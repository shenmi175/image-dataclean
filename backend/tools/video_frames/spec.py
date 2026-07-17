from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import OutputDirectoryParams


class VideoFramesParams(OutputDirectoryParams):
    input_files: list[Path] = Field(default_factory=list, title="视频文件")
    input_dir: Path | None = Field(default=None, title="视频目录")
    recursive: bool = Field(default=True, title="递归扫描子目录")
    frame_interval: int = Field(default=10, ge=1, le=1_000_000, title="抽帧间隔")
    resize: bool = Field(default=True, title="调整图片尺寸")
    width: int = Field(default=640, ge=1, le=32768, title="宽度")
    height: int = Field(default=640, ge=1, le=32768, title="高度")
    resize_mode: Literal["letterbox", "direct"] = Field(
        default="letterbox", title="缩放方式"
    )

    @model_validator(mode="after")
    def validate_sources(self) -> VideoFramesParams:
        if not self.input_files and self.input_dir is None:
            raise ValueError("至少选择一个视频文件或一个视频目录")
        if self.input_dir is not None and not self.input_dir.expanduser().is_dir():
            raise ValueError(f"视频目录不存在或不是目录: {self.input_dir}")
        invalid_files = [path for path in self.input_files if not path.expanduser().is_file()]
        if invalid_files:
            raise ValueError(f"视频文件不存在或不是文件: {invalid_files[0]}")
        return self
