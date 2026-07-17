import json
from pathlib import Path

from PIL import Image

from backend.tools.labelme_to_yolo import LabelmeSource, LabelmeToYoloParams, LabelmeToYoloTool
from tests.tool_test_utils import RecordingContext


def test_labelme_to_yolo_builds_dataset_and_reports(tmp_path: Path) -> None:
    source = tmp_path / "labelme"
    source.mkdir()
    Image.new("RGB", (100, 50), (30, 60, 90)).save(source / "图像.jpg")
    (source / "图像.json").write_text(
        json.dumps(
            {
                "imagePath": "图像.jpg",
                "imageWidth": 100,
                "imageHeight": 50,
                "shapes": [
                    {
                        "label": "floor",
                        "shape_type": "rectangle",
                        "points": [[10, 10], [90, 40]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "task"
    result = LabelmeToYoloTool().run(
        LabelmeToYoloParams(
            sources=[LabelmeSource(name="室内", path=source)],
            classes=["floor"],
            output_dir=tmp_path / "root",
        ),
        RecordingContext(output),
    )

    labels = list((output / "labels" / "train").glob("*.txt"))
    assert result["success_count"] == 1
    assert labels[0].read_text(encoding="utf-8").startswith("0 0.100000 0.200000")
    assert (output / "summary.json").is_file()
    assert (output / "files.csv").is_file()
