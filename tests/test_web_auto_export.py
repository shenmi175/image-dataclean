import json
from pathlib import Path

from PIL import Image

from backend.tools.web_auto_export import WebAutoExportParams, WebAutoExportTool
from backend.tools.web_auto_export.common import annotation_path
from tests.tool_test_utils import RecordingContext


def make_web_auto_source(tmp_path: Path) -> tuple[Path, Path]:
    images = tmp_path / "images"
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    image = images / "train" / "a.jpg"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (32, 24), (120, 80, 30)).save(image)
    annotation_path(annotations, "train/a.jpg").write_text(
        json.dumps([{"class_name": "chair", "polygon": [[1, 1], [20, 1], [20, 20]]}]),
        encoding="utf-8",
    )
    return images, annotations


def test_web_auto_exports_labelme_and_coco(tmp_path: Path) -> None:
    images, annotations = make_web_auto_source(tmp_path)
    for output_format in ("labelme", "coco"):
        output = tmp_path / f"task-{output_format}"
        result = WebAutoExportTool().run(
            WebAutoExportParams(
                image_dir=images,
                annotation_dir=annotations,
                output_dir=tmp_path / "root",
                output_format=output_format,
                splits=["train"],
                classes=["chair"],
            ),
            RecordingContext(output),
        )
        assert result["success_count"] == 1
        expected = (
            output / "labelme" / "train" / "a.json"
            if output_format == "labelme"
            else output / "annotations" / "instances_train.json"
        )
        assert expected.is_file()
        assert (output / "summary.json").is_file()
