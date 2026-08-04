from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.tools import frame_deduplicator
from backend.tools.frame_deduplicator import (
    FrameDeduplicatorParams,
    FrameDeduplicatorTool,
)
from backend.tools.frame_deduplicator.executor import (
    EmbeddingResult,
    ImageItem,
    build_sequences,
    decide_frames,
    natural_key,
)
from backend.tools.frame_deduplicator.model import ModelFile, ensure_model_files
from tests.tool_test_utils import RecordingContext

executor = frame_deduplicator.executor


def normalized(*values: float) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def item(root: Path, relative: str, digest: str) -> ImageItem:
    path = root / relative
    return ImageItem(path, Path(relative), 10, digest)


def save_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 16), color).save(path)


def fake_embedder(vectors: dict[str, np.ndarray]):
    def embed(
        items: list[ImageItem],
        batch_size: int,
        requested_device: str,
        context: RecordingContext,
        **kwargs: object,
    ) -> EmbeddingResult:
        return EmbeddingResult(
            {entry.path: vectors[entry.path.name] for entry in items},
            {},
            "cpu",
            batch_size,
        )

    return embed


def test_natural_sort_orders_numeric_frame_names() -> None:
    paths = [Path("frame_10.jpg"), Path("frame_2.jpg"), Path("frame_1.jpg")]

    assert sorted(paths, key=natural_key) == [
        Path("frame_1.jpg"),
        Path("frame_2.jpg"),
        Path("frame_10.jpg"),
    ]


def test_dynamic_representative_changes_on_new_scene(tmp_path: Path) -> None:
    items = [
        item(tmp_path, "frame_1.jpg", "a"),
        item(tmp_path, "frame_2.jpg", "b"),
        item(tmp_path, "frame_3.jpg", "c"),
        item(tmp_path, "frame_4.jpg", "d"),
    ]
    embeddings = {
        items[0].path: normalized(1.0, 0.0),
        items[1].path: normalized(0.99, 0.03),
        items[2].path: normalized(0.0, 1.0),
        items[3].path: normalized(0.03, 0.99),
    }

    decisions = decide_frames([items], embeddings, {}, 0.95)

    assert [decision.status for decision in decisions] == [
        "kept",
        "similar",
        "kept",
        "similar",
    ]
    assert decisions[1].representative == Path("frame_1.jpg")
    assert decisions[3].representative == Path("frame_3.jpg")


def test_scope_resets_representative_and_exact_hashes_per_directory(
    tmp_path: Path,
) -> None:
    first = item(tmp_path, "a/frame.jpg", "same")
    second = item(tmp_path, "b/frame.jpg", "same")
    embeddings = {first.path: normalized(1, 0), second.path: normalized(1, 0)}

    directory = decide_frames(
        build_sequences([first, second], "directory"), embeddings, {}, 0.95
    )
    global_scope = decide_frames(
        build_sequences([first, second], "global"), embeddings, {}, 0.95
    )

    assert [decision.status for decision in directory] == ["kept", "kept"]
    assert [decision.status for decision in global_scope] == [
        "kept",
        "exact_duplicate",
    ]


def test_exact_duplicate_is_removed_after_a_scene_change(tmp_path: Path) -> None:
    first = item(tmp_path, "1.jpg", "same")
    middle = item(tmp_path, "2.jpg", "different")
    repeated = item(tmp_path, "3.jpg", "same")
    embeddings = {
        first.path: normalized(1, 0),
        middle.path: normalized(0, 1),
    }

    decisions = decide_frames([[first, middle, repeated]], embeddings, {}, 0.95)

    assert [decision.status for decision in decisions] == [
        "kept",
        "kept",
        "exact_duplicate",
    ]
    assert decisions[-1].representative == Path("1.jpg")


def test_params_require_confirmation_and_external_report_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="永久删除"):
        FrameDeduplicatorParams(
            input_dir=source,
            output_dir=tmp_path / "output",
            operation="delete",
        )
    with pytest.raises(ValueError, match="输出目录不能"):
        FrameDeduplicatorParams(input_dir=source, output_dir=source / "output")


def test_copy_mode_preserves_structure_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    first = source / "scene" / "frame_1.jpg"
    similar = source / "scene" / "frame_2.jpg"
    next_scene = source / "scene" / "frame_3.jpg"
    save_image(first, (255, 0, 0))
    save_image(similar, (250, 0, 0))
    save_image(next_scene, (0, 0, 255))
    monkeypatch.setattr(
        executor,
        "embed_images",
        fake_embedder(
            {
                first.name: normalized(1, 0),
                similar.name: normalized(0.99, 0.02),
                next_scene.name: normalized(0, 1),
            }
        ),
    )
    output = tmp_path / "task-output"

    result = FrameDeduplicatorTool().run(
        FrameDeduplicatorParams(input_dir=source, output_dir=tmp_path / "reports"),
        RecordingContext(output),
    )

    assert first.is_file() and similar.is_file() and next_scene.is_file()
    assert (output / "cleaned" / "scene" / first.name).is_file()
    assert not (output / "cleaned" / "scene" / similar.name).exists()
    assert (output / "cleaned" / "scene" / next_scene.name).is_file()
    assert (output / "summary.json").is_file()
    assert (output / "decisions.csv").is_file()
    assert result["success_count"] == 3


def test_delete_mode_only_deletes_redundant_frames_after_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    first = source / "frame_1.jpg"
    similar = source / "frame_2.jpg"
    save_image(first, (255, 0, 0))
    save_image(similar, (250, 0, 0))
    monkeypatch.setattr(
        executor,
        "embed_images",
        fake_embedder(
            {first.name: normalized(1, 0), similar.name: normalized(0.99, 0.02)}
        ),
    )
    output = tmp_path / "task-output"

    FrameDeduplicatorTool().run(
        FrameDeduplicatorParams(
            input_dir=source,
            output_dir=tmp_path / "reports",
            operation="delete",
            confirm_delete=True,
        ),
        RecordingContext(output),
    )

    assert first.is_file()
    assert not similar.exists()
    assert (output / "deletion_plan.csv").is_file()
    assert (output / "decisions.csv").is_file()


def test_model_files_are_verified_and_reused(tmp_path: Path) -> None:
    payload = b"local model bytes"
    expected = ModelFile("weights.bin", hashlib.sha256(payload).hexdigest(), len(payload))
    downloads: list[str] = []

    def downloader(model_file: ModelFile, target: Path, checkpoint) -> None:  # type: ignore[no-untyped-def]
        downloads.append(model_file.name)
        target.write_bytes(payload)

    model_dir = tmp_path / "models"
    assert ensure_model_files(model_dir, [expected], downloader=downloader) == model_dir
    assert downloads == ["weights.bin"]

    ensure_model_files(model_dir, [expected], downloader=downloader)
    assert downloads == ["weights.bin"]

    (model_dir / "weights.bin").write_bytes(b"corrupt")
    ensure_model_files(model_dir, [expected], downloader=downloader)
    assert downloads == ["weights.bin", "weights.bin"]
