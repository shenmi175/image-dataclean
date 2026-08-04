from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.tools.base import TaskCancelled, TaskContext
from backend.tools.image_classifier import ImageClassifierParams, ImageClassifierTool
from backend.tools.image_classifier.executor import (
    classify_pixels,
    discover_images,
    output_relative_path,
)


class RecordingContext(TaskContext):
    def __init__(
        self,
        output_path: Path,
        resolution: tuple[str, str] = ("skip", "current"),
        parallel_workers: int = 1,
    ) -> None:
        self.task_id = "classifier-test"
        self.output_path = str(output_path)
        self.parallel_workers = parallel_workers
        self.resolution = resolution
        self.progress: list[tuple[int, int | None]] = []
        self.logs: list[str] = []
        self.failures: list[tuple[str, str]] = []
        self.conflicts: list[tuple[str, str]] = []
        self.cancelled = False

    def wait_if_paused(self) -> None:
        return

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled

    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
        *,
        success_count: int | None = None,
        failure_count: int | None = None,
        force: bool = False,
    ) -> None:
        self.progress.append((current, total))

    def log(self, level: str, message: str) -> None:
        self.logs.append(message)

    def record_failure(self, item: str, error: str) -> None:
        self.failures.append((item, error))

    def request_conflict_resolution(self, source: str, target: str) -> dict[str, str]:
        self.conflicts.append((source, target))
        return {"action": self.resolution[0], "scope": self.resolution[1]}


def save_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color).save(path)


def test_pixel_classifier_matches_rgb_and_grayscale_examples() -> None:
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255
    grayscale = np.full((8, 8, 3), 127, dtype=np.uint8)

    assert classify_pixels(rgb)[0] == "rgb"
    assert classify_pixels(grayscale)[0] == "ir"
    assert classify_pixels(grayscale)[1].gray_ratio == 1.0


@pytest.mark.parametrize(
    ("layout", "expected"),
    [
        ("all-suffixed", "22102202_rgb/a_rgb/000510_rgb.jpg"),
        ("leaf-suffixed", "22102202/a_rgb/000510_rgb.jpg"),
        ("category-root", "rgb/22102202/a/000510_rgb.jpg"),
    ],
)
def test_output_layouts(layout: str, expected: str) -> None:
    assert str(output_relative_path(Path("22102202/a/000510.jpg"), "rgb", layout)) == expected


def test_discovery_respects_recursive_and_ignores_non_images(tmp_path: Path) -> None:
    source = tmp_path / "source"
    save_image(source / "top.jpg", (255, 0, 0))
    save_image(source / "nested" / "child.png", (100, 100, 100))
    (source / "notes.txt").write_text("not an image", encoding="utf-8")

    flat = discover_images(
        ImageClassifierParams(input_dir=source, output_dir=tmp_path / "output", recursive=False)
    )
    recursive = discover_images(
        ImageClassifierParams(input_dir=source, output_dir=tmp_path / "output", recursive=True)
    )

    assert [relative.as_posix() for _, relative in flat] == ["top.jpg"]
    assert [relative.as_posix() for _, relative in recursive] == [
        "nested/child.png",
        "top.jpg",
    ]


def test_tool_classifies_and_preserves_suffixed_structure(tmp_path: Path) -> None:
    source = tmp_path / "输入"
    save_image(source / "22102202" / "彩色.jpg", (255, 0, 0))
    save_image(source / "22102230" / "灰度.jpg", (80, 80, 80))
    output = tmp_path / "任务输出"
    context = RecordingContext(output)
    params = ImageClassifierParams(input_dir=source, output_dir=tmp_path / "output-root")

    context.parallel_workers = 3
    result = ImageClassifierTool().run(params, context)

    assert (output / "22102202_rgb" / "彩色_rgb.jpg").is_file()
    assert (output / "22102230_ir" / "灰度_ir.jpg").is_file()
    assert result["success_count"] == 2
    assert result["failure_count"] == 0


def test_move_removes_source_only_after_output_is_written(tmp_path: Path) -> None:
    source = tmp_path / "source"
    image = source / "gray.png"
    save_image(image, (20, 20, 20))
    output = tmp_path / "task-output"
    params = ImageClassifierParams(
        input_dir=source,
        output_dir=tmp_path / "output-root",
        operation="move",
    )

    ImageClassifierTool().run(params, RecordingContext(output))

    assert not image.exists()
    assert (output / "gray_ir.png").is_file()


def test_tool_can_output_only_rgb_images(tmp_path: Path) -> None:
    source = tmp_path / "source"
    save_image(source / "room" / "color.jpg", (255, 0, 0))
    save_image(source / "room" / "gray.jpg", (80, 80, 80))
    output = tmp_path / "task-output"
    params = ImageClassifierParams(
        input_dir=source,
        output_dir=tmp_path / "output-root",
        output_category="rgb",
        layout="category-root",
    )

    result = ImageClassifierTool().run(params, RecordingContext(output))

    assert (output / "rgb" / "room" / "color_rgb.jpg").is_file()
    assert not (output / "ir").exists()
    assert not (output / "rgb" / "room" / "gray_ir.jpg").exists()
    assert result["success_count"] == 1
    assert result["failure_count"] == 0


def test_conflict_can_be_renamed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    image = source / "photo.jpg"
    save_image(image, (255, 0, 0))
    output = tmp_path / "task-output"
    existing = output / "photo_rgb.jpg"
    save_image(existing, (0, 255, 0))
    context = RecordingContext(output, resolution=("rename", "remaining"))
    params = ImageClassifierParams(input_dir=source, output_dir=tmp_path / "output-root")

    result = ImageClassifierTool().run(params, context)

    assert existing.is_file()
    assert (output / "photo_rgb_1.jpg").is_file()
    assert result["success_count"] == 1
    assert len(context.conflicts) == 1


def test_output_cannot_be_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="输出目录不能"):
        ImageClassifierParams(input_dir=source, output_dir=source / "classified")
