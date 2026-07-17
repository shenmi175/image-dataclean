from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from backend.tools.common import image_files


def split_images(image_root: Path, split: str) -> list[Path]:
    root = image_root if split == "." else image_root / split
    if not root.is_dir():
        raise FileNotFoundError(f"数据划分目录不存在: {root}")
    return image_files(root)


def annotation_path(annotation_root: Path, relative_image: str) -> Path:
    image_id = uuid.uuid5(uuid.NAMESPACE_URL, relative_image).hex[:16]
    return annotation_root / f"{image_id}.json"


def load_annotations(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"标注文件必须是 JSON 数组: {path}")
    return [item for item in payload if isinstance(item, dict)]


def annotation_label(annotation: dict[str, Any]) -> str:
    return str(annotation.get("class_name") or annotation.get("raw_label") or "").strip()


def polygon(annotation: dict[str, Any]) -> list[list[float]] | None:
    raw = annotation.get("polygon")
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    points = [[float(point[0]), float(point[1])] for point in raw if len(point) >= 2]
    return points if len(points) >= 3 else None
