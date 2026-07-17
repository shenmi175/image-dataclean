from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from backend.tools.common import (
    find_image,
    read_yolo_classes,
    read_yolo_lines,
    safe_relative_path,
    validate_yolo_line,
)


@dataclass(frozen=True)
class Polygon:
    label: str
    points: list[tuple[float, float]]


@dataclass(frozen=True)
class VisualSample:
    key: str
    image: Path
    polygons: list[Polygon]


def labelme_samples(root: Path) -> list[VisualSample]:
    samples = []
    for json_path in sorted(root.rglob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data.get("shapes"), list):
            continue
        raw_image = data.get("imagePath")
        image = (json_path.parent / str(raw_image)).resolve() if raw_image else None
        if image is None or not image.is_file():
            image = find_image(json_path.parent, json_path.stem)
        if image is None:
            raise FileNotFoundError(f"Labelme 标注缺少图像: {json_path}")
        polygons = []
        for shape in data["shapes"]:
            raw = shape.get("points") or []
            points = [(float(point[0]), float(point[1])) for point in raw if len(point) >= 2]
            if shape.get("shape_type") == "rectangle" and len(points) == 2:
                (x1, y1), (x2, y2) = points
                points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            if len(points) >= 3:
                polygons.append(Polygon(str(shape.get("label") or ""), points))
        samples.append(VisualSample(json_path.relative_to(root).as_posix(), image, polygons))
    return samples


def yolo_samples(
    root: Path, data_yaml: Path | None, explicit_classes: list[str]
) -> list[VisualSample]:
    classes = explicit_classes or read_yolo_classes(root, data_yaml)
    samples = []
    for split in ("train", "val", "test"):
        label_dir = root / "labels" / split
        image_dir = root / "images" / split
        if not label_dir.is_dir():
            continue
        for label_path in sorted(label_dir.glob("*.txt")):
            image = find_image(image_dir, label_path.stem)
            if image is None:
                raise FileNotFoundError(f"YOLO 标签缺少图像: {label_path}")
            with Image.open(image) as opened:
                width, height = opened.size
            polygons = []
            for line in read_yolo_lines(label_path):
                class_id, coords = validate_yolo_line(line, label_path)
                if class_id >= len(classes):
                    raise ValueError(f"类别 ID 超出 names 范围: {label_path}: {class_id}")
                points = [
                    (coords[index] * width, coords[index + 1] * height)
                    for index in range(0, len(coords), 2)
                ]
                polygons.append(Polygon(classes[class_id], points))
            samples.append(VisualSample(f"{split}/{label_path.name}", image, polygons))
    return samples


def coco_samples(image_root: Path, annotation_file: Path) -> list[VisualSample]:
    data = json.loads(annotation_file.read_text(encoding="utf-8"))
    categories = {int(item["id"]): str(item["name"]) for item in data.get("categories", [])}
    grouped: dict[int, list[Polygon]] = defaultdict(list)
    for annotation in data.get("annotations", []):
        label = categories.get(int(annotation["category_id"]), str(annotation["category_id"]))
        segmentation = annotation.get("segmentation")
        if not isinstance(segmentation, list):
            continue
        for coords in segmentation:
            if isinstance(coords, list) and len(coords) >= 6 and len(coords) % 2 == 0:
                grouped[int(annotation["image_id"])].append(
                    Polygon(
                        label,
                        [
                            (float(coords[index]), float(coords[index + 1]))
                            for index in range(0, len(coords), 2)
                        ],
                    )
                )
    return [
        VisualSample(
            str(image["file_name"]),
            image_root / safe_relative_path(str(image["file_name"])),
            grouped[int(image["id"])],
        )
        for image in data.get("images", [])
    ]
