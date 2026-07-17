from pathlib import Path

from PIL import Image

from backend.tools.dataset_common import write_yolo_yaml
from backend.tools.yolo_merge import YoloMergeParams, YoloMergeTool, YoloSource
from tests.tool_test_utils import RecordingContext


def make_source(root: Path, name: str, class_name: str) -> None:
    image = root / "images" / "train" / f"{name}.jpg"
    label = root / "labels" / "train" / f"{name}.txt"
    image.parent.mkdir(parents=True, exist_ok=True)
    label.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), (10, 20, 30)).save(image)
    label.write_text("0 0.1 0.1 0.9 0.1 0.9 0.9\n", encoding="utf-8")
    write_yolo_yaml(root, [class_name], ["train"])


def test_yolo_merge_maps_classes_and_prefixes_sources(tmp_path: Path) -> None:
    floor = tmp_path / "floor"
    chair = tmp_path / "chair"
    make_source(floor, "same", "floor")
    make_source(chair, "same", "office_chair")
    output = tmp_path / "task"
    result = YoloMergeTool().run(
        YoloMergeParams(
            sources=[
                YoloSource(name="floor-set", path=floor),
                YoloSource(name="chair-set", path=chair, class_map={"office_chair": "chair"}),
            ],
            output_classes=["floor", "chair"],
            output_dir=tmp_path / "root",
            splits=["train"],
        ),
        RecordingContext(output),
    )

    labels = sorted((output / "labels" / "train").glob("*.txt"))
    assert result["success_count"] == 2
    assert len(labels) == 2
    assert {path.read_text(encoding="utf-8").split()[0] for path in labels} == {"0", "1"}
    assert (output / "manifest.csv").is_file()
