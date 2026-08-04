from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class FrameDeduplicatorParams(OutputDirectoryParams):
    input_dir: Path = Field(title="图片目录")
    recursive: bool = Field(default=True, title="递归扫描子目录")
    comparison_scope: Literal["directory", "global"] = Field(
        default="directory", title="比较范围"
    )
    operation: Literal["copy", "delete"] = Field(default="copy", title="输出方式")
    confirm_delete: bool = Field(default=False, title="确认永久删除冗余帧")
    similarity_threshold: float = Field(
        default=0.95,
        ge=0.8,
        le=1.0,
        multiple_of=0.001,
        title="相似度阈值",
    )
    batch_size: int = Field(default=16, ge=1, le=128, title="推理批大小")
    device: Literal["auto", "cpu", "cuda"] = Field(default="auto", title="推理设备")

    @model_validator(mode="after")
    def validate_paths_and_operation(self) -> FrameDeduplicatorParams:
        source = self.input_dir.expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"图片目录不存在或不是目录: {self.input_dir}")
        validate_output_outside(self.output_dir, [source], "图片目录")
        if self.operation == "delete" and not self.confirm_delete:
            raise ValueError("原地清理会永久删除冗余帧，请先勾选确认")
        return self
