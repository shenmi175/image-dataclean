from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Literal

from backend.tools.base import TaskContext

TransferMode = Literal["copy", "move"]


def available_path(target: Path) -> Path:
    index = 1
    while target.exists():
        target = target.with_name(f"{target.stem}_{index}{target.suffix}")
        index += 1
    return target


def transfer_file(
    source: Path,
    target: Path,
    context: TaskContext,
    *,
    mode: TransferMode = "copy",
) -> Path | None:
    """Copy or move through a temporary file, resolving target conflicts consistently."""
    if mode not in ("copy", "move"):
        raise ValueError(f"未知文件操作: {mode}")
    if target.exists():
        action = context.request_conflict_resolution(str(source), str(target))["action"]
        if action == "skip":
            return None
        if action == "rename":
            target = available_path(target)
        elif action != "overwrite":
            raise ValueError(f"未知冲突处理动作: {action}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
        if mode == "move":
            source.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return target
