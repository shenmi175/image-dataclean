from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path


def require_directory(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label}不存在或不是目录: {path}")
    return resolved


def require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label}不存在或不是文件: {path}")
    return resolved


def validate_output_outside(output: Path, sources: Iterable[Path], label: str = "输入目录") -> Path:
    resolved_output = output.expanduser().resolve()
    if resolved_output.exists() and not resolved_output.is_dir():
        raise ValueError(f"输出路径不是目录: {output}")
    for source in sources:
        resolved_source = source.expanduser().resolve()
        if resolved_output == resolved_source or resolved_source in resolved_output.parents:
            raise ValueError(f"输出目录不能是{label}或位于其内部")
    return resolved_output


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+", "_", value.strip())
    return normalized.strip("_") or "source"


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"不安全的相对路径: {value}")
    return path
