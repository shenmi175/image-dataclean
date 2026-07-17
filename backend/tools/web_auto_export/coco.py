from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from backend.core.compat import UTC
from backend.tools.web_auto_export.common import annotation_label, polygon


def build_coco(
    items: list[tuple[Path, str, list[dict[str, Any]]]], classes: list[str]
) -> tuple[dict[str, Any], int]:
    category_ids = {name: index + 1 for index, name in enumerate(classes)}
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    skipped = 0
    annotation_id = 1
    for image_id, (image_path, file_name, source_annotations) in enumerate(items, start=1):
        with Image.open(image_path) as opened:
            width, height = opened.size
        images.append({"id": image_id, "file_name": file_name, "width": width, "height": height})
        for source in source_annotations:
            points = polygon(source)
            category_id = category_ids.get(annotation_label(source))
            if points is None or category_id is None:
                skipped += 1
                continue
            flat = [value for point in points for value in point]
            xs, ys = flat[0::2], flat[1::2]
            area = (
                abs(
                    sum(
                        xs[index] * ys[(index + 1) % len(xs)]
                        - xs[(index + 1) % len(xs)] * ys[index]
                        for index in range(len(xs))
                    )
                )
                / 2
            )
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": category_id,
                    "segmentation": [flat],
                    "area": round(area, 2),
                    "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
                    "iscrowd": 0,
                }
            )
            annotation_id += 1
    return (
        {
            "info": {
                "description": "Exported from web-auto",
                "date_created": datetime.now(UTC).isoformat(),
            },
            "licenses": [],
            "images": images,
            "annotations": annotations,
            "categories": [
                {"id": index + 1, "name": name, "supercategory": "object"}
                for index, name in enumerate(classes)
            ],
        },
        skipped,
    )
