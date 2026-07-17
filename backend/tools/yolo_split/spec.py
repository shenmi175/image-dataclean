from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class YoloSplitParams(OutputDirectoryParams):
    input_dir: Path = Field(title="YOLO 数据集目录")
    val_ratio: float = Field(default=0.15, gt=0.0, lt=1.0, title="验证集比例")
    seed: int = Field(default=20260707, title="随机种子")
    existing_val_policy: Literal["preserve", "resplit"] = Field(
        default="preserve", title="已有验证集处理"
    )

    @model_validator(mode="after")
    def validate_paths(self) -> YoloSplitParams:
        if not self.input_dir.expanduser().is_dir():
            raise ValueError(f"YOLO 数据集不存在: {self.input_dir}")
        validate_output_outside(self.output_dir, [self.input_dir], "输入数据集")
        return self
