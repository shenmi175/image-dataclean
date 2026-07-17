from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class WebAutoExportParams(OutputDirectoryParams):
    image_dir: Path = Field(title="图像根目录")
    annotation_dir: Path = Field(title="web-auto 标注目录")
    project_json: Path | None = Field(default=None, title="web_auto_project.json")
    output_format: Literal["labelme", "coco"] = Field(default="labelme", title="输出格式")
    splits: list[str] = Field(
        default_factory=lambda: ["train", "val"], min_length=1, title="数据划分"
    )
    classes: list[str] = Field(default_factory=list, title="类别顺序（可选）")
    copy_images: bool = Field(default=True, title="复制图片")
    embed_image_data: bool = Field(default=False, title="Labelme 内嵌图片")
    include_all: bool = Field(default=True, title="COCO 生成全量文件")
    strict_missing: bool = Field(default=False, title="缺少标注时失败")

    @field_validator("splits", "classes")
    @classmethod
    def clean_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("列表内容不能重复")
        return cleaned

    @model_validator(mode="after")
    def validate_paths(self) -> WebAutoExportParams:
        for path, label in ((self.image_dir, "图像目录"), (self.annotation_dir, "标注目录")):
            if not path.expanduser().is_dir():
                raise ValueError(f"{label}不存在: {path}")
        if self.project_json is not None and not self.project_json.expanduser().is_file():
            raise ValueError(f"项目文件不存在: {self.project_json}")
        validate_output_outside(self.output_dir, [self.image_dir, self.annotation_dir])
        return self
