from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class CocoToLabelmeParams(OutputDirectoryParams):
    coco_json: Path = Field(title="COCO 标注 JSON")
    image_dir: Path = Field(title="图像根目录")
    copy_images: bool = Field(default=True, title="复制图片")
    embed_image_data: bool = Field(default=False, title="内嵌图片数据")
    unsupported_policy: Literal["skip", "error"] = Field(default="skip", title="不支持标注处理")

    @model_validator(mode="after")
    def validate_paths(self) -> CocoToLabelmeParams:
        if not self.coco_json.expanduser().is_file():
            raise ValueError(f"COCO JSON 不存在: {self.coco_json}")
        if not self.image_dir.expanduser().is_dir():
            raise ValueError(f"图像目录不存在: {self.image_dir}")
        validate_output_outside(self.output_dir, [self.image_dir], "图像目录")
        return self
