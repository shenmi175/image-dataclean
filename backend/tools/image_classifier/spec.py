from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class ImageClassifierParams(OutputDirectoryParams):
    input_dir: Path = Field(title="源图像目录")
    recursive: bool = Field(default=True, title="递归扫描子目录")
    operation: Literal["copy", "move"] = Field(default="copy", title="文件操作")
    output_category: Literal["all", "rgb", "ir"] = Field(
        default="all", title="输出类别"
    )
    layout: Literal["all-suffixed", "leaf-suffixed", "category-root"] = Field(
        default="all-suffixed", title="输出目录结构"
    )
    threshold: float = Field(default=0.90, ge=0.0, le=1.0, title="灰度像素比例阈值")
    tolerance: int = Field(default=2, ge=0, le=255, title="通道差容差")

    @model_validator(mode="after")
    def validate_paths(self) -> ImageClassifierParams:
        source = self.input_dir.expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"源图像目录不存在或不是目录: {self.input_dir}")
        validate_output_outside(self.output_dir, [self.input_dir], "源图像目录")
        return self
