from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml


def validate_yolo_line(line: str, source: Path | str) -> tuple[int, list[float]]:
    parts = line.split()
    if len(parts) < 7 or (len(parts) - 1) % 2:
        raise ValueError(f"无效 YOLO 分割标注: {source}: {line}")
    class_id = int(parts[0])
    coords = [float(value) for value in parts[1:]]
    if any(value < 0.0 or value > 1.0 for value in coords):
        raise ValueError(f"YOLO 坐标超出 [0,1]: {source}: {line}")
    return class_id, coords


def read_yolo_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_yolo_classes(dataset_root: Path, data_yaml: Path | None = None) -> list[str]:
    yaml_path = data_yaml or dataset_root / "data.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"找不到 YOLO data.yaml: {yaml_path}")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    names = data.get("names")
    if isinstance(names, list):
        return [str(item) for item in names]
    if isinstance(names, dict):
        return [str(names[key]) for key in sorted(names, key=lambda value: int(value))]
    raise ValueError(f"data.yaml 缺少有效 names: {yaml_path}")


def write_yolo_yaml(output: Path, classes: list[str], splits: Iterable[str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    split_set = set(splits)
    payload: dict[str, Any] = {"path": output.as_posix()}
    for split in ("train", "val", "test"):
        if split in split_set:
            payload[split] = f"images/{split}"
    payload["nc"] = len(classes)
    payload["names"] = {index: name for index, name in enumerate(classes)}
    (output / "data.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
