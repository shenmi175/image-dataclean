from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from PIL import Image

from backend.tools.web_auto_export.common import annotation_label, polygon


def labelme_document(
    image: Path,
    output_json: Path,
    annotations: list[dict[str, Any]],
    *,
    copied_image: Path | None,
    embed_image_data: bool,
) -> tuple[dict[str, Any], int]:
    with Image.open(image) as opened:
        width, height = opened.size
    shapes = []
    skipped = 0
    for annotation in annotations:
        points = polygon(annotation)
        label = annotation_label(annotation)
        if points is None or not label:
            skipped += 1
            continue
        shapes.append(
            {
                "label": label,
                "points": points,
                "group_id": None,
                "description": "",
                "shape_type": "polygon",
                "flags": {},
                "mask": None,
            }
        )
    image_path = (
        copied_image.name
        if copied_image is not None
        else Path(os.path.relpath(image, output_json.parent)).as_posix()
    )
    return (
        {
            "version": "5.8.3",
            "flags": {},
            "shapes": shapes,
            "imagePath": image_path,
            "imageData": base64.b64encode(image.read_bytes()).decode("ascii")
            if embed_image_data
            else None,
            "imageHeight": height,
            "imageWidth": width,
        },
        skipped,
    )
