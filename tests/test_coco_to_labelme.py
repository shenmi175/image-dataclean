import json
from pathlib import Path

from PIL import Image

from backend.tools.coco_to_labelme import CocoToLabelmeParams, CocoToLabelmeTool
from tests.tool_test_utils import RecordingContext


def test_coco_to_labelme_preserves_multiple_polygons(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (40, 30), (0, 0, 0)).save(images / "a.jpg")
    coco = tmp_path / "instances.json"
    coco.write_text(
        json.dumps(
            {
                "categories": [{"id": 1, "name": "floor"}],
                "images": [{"id": 1, "file_name": "a.jpg", "width": 40, "height": 30}],
                "annotations": [
                    {
                        "id": 7,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [[0, 0, 10, 0, 10, 10], [20, 20, 30, 20, 30, 30]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "task"
    CocoToLabelmeTool().run(
        CocoToLabelmeParams(coco_json=coco, image_dir=images, output_dir=tmp_path / "root"),
        RecordingContext(output),
    )

    labelme = json.loads((output / "labelme" / "a.json").read_text(encoding="utf-8"))
    assert len(labelme["shapes"]) == 2
    assert labelme["shapes"][0]["group_id"] == 7
