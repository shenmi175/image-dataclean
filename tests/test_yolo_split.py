import hashlib
from pathlib import Path

from PIL import Image

from backend.tools.dataset_common import write_yolo_yaml
from backend.tools.yolo_split import YoloSplitParams, YoloSplitTool
from tests.tool_test_utils import RecordingContext


def add_sample(root: Path, split: str, stem: str) -> None:
    image = root / "images" / split / f"{stem}.jpg"
    label = root / "labels" / split / f"{stem}.txt"
    image.parent.mkdir(parents=True, exist_ok=True)
    label.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), (100, 50, 20)).save(image)
    label.write_text("0 0.1 0.1 0.9 0.1 0.9 0.9\n", encoding="utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_yolo_split_preserves_existing_val_and_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    for index in range(4):
        add_sample(source, "train", f"train{index}")
    add_sample(source, "val", "existing")
    write_yolo_yaml(source, ["floor"], ["train", "val"])
    before = tree_digest(source)
    output = tmp_path / "task"
    result = YoloSplitTool().run(
        YoloSplitParams(
            input_dir=source,
            output_dir=tmp_path / "root",
            val_ratio=0.4,
            existing_val_policy="preserve",
            seed=3,
        ),
        RecordingContext(output),
    )

    assert result["success_count"] == 5
    assert len(list((output / "images" / "val").glob("*.jpg"))) == 2
    assert (output / "images" / "val" / "existing.jpg").is_file()
    assert tree_digest(source) == before
