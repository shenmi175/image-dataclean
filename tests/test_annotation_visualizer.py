import json
from pathlib import Path

from PIL import Image

from backend.tools.annotation_visualizer import AnnotationVisualizerParams, AnnotationVisualizerTool
from backend.tools.dataset_common import write_yolo_yaml
from tests.tool_test_utils import RecordingContext


def test_annotation_visualizer_renders_labelme_and_mosaic(tmp_path: Path) -> None:
    source = tmp_path / "labelme"
    source.mkdir()
    Image.new("RGB", (64, 48), (30, 30, 30)).save(source / "a.jpg")
    (source / "a.json").write_text(
        json.dumps(
            {
                "imagePath": "a.jpg",
                "shapes": [
                    {
                        "label": "floor",
                        "shape_type": "polygon",
                        "points": [[1, 1], [60, 1], [60, 40]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "task"
    result = AnnotationVisualizerTool().run(
        AnnotationVisualizerParams(
            annotation_format="labelme",
            input_dir=source,
            output_dir=tmp_path / "root",
            limit=1,
            sample_mode="first",
        ),
        RecordingContext(output),
    )

    assert result["success_count"] == 1
    assert len(list((output / "images").glob("*.jpg"))) == 1
    assert (output / "mosaic_01.jpg").is_file()
    assert (output / "selected_samples.csv").is_file()


def test_annotation_visualizer_supports_yolo_and_coco(tmp_path: Path) -> None:
    yolo = tmp_path / "yolo"
    image = yolo / "images" / "train" / "a.jpg"
    label = yolo / "labels" / "train" / "a.txt"
    image.parent.mkdir(parents=True)
    label.parent.mkdir(parents=True)
    Image.new("RGB", (40, 30), (20, 30, 40)).save(image)
    label.write_text("0 0.1 0.1 0.9 0.1 0.9 0.9\n", encoding="utf-8")
    write_yolo_yaml(yolo, ["floor"], ["train"])

    coco_images = tmp_path / "coco-images"
    coco_images.mkdir()
    Image.new("RGB", (40, 30), (20, 30, 40)).save(coco_images / "a.jpg")
    coco_json = tmp_path / "coco.json"
    coco_json.write_text(
        json.dumps(
            {
                "categories": [{"id": 1, "name": "floor"}],
                "images": [{"id": 1, "file_name": "a.jpg", "width": 40, "height": 30}],
                "annotations": [
                    {
                        "id": 1,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [[1, 1, 30, 1, 30, 20]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = [
        AnnotationVisualizerParams(
            annotation_format="yolo", input_dir=yolo, output_dir=tmp_path / "root"
        ),
        AnnotationVisualizerParams(
            annotation_format="coco",
            input_dir=coco_images,
            annotation_file=coco_json,
            output_dir=tmp_path / "root",
        ),
    ]
    for index, params in enumerate(cases):
        output = tmp_path / f"task-{index}"
        result = AnnotationVisualizerTool().run(params, RecordingContext(output))
        assert result["success_count"] == 1
        assert (output / "mosaic_01.jpg").is_file()
