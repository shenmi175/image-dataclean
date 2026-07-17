from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.tools.common import OutputDirectoryParams, validate_output_outside


class LabelmeSource(BaseModel):
    name: str = Field(min_length=1, title="来源名称")
    path: Path = Field(title="Labelme 目录")

    @field_validator("path")
    @classmethod
    def source_exists(cls, value: Path) -> Path:
        if not value.expanduser().is_dir():
            raise ValueError(f"Labelme 目录不存在: {value}")
        return value


class LabelmeToYoloParams(OutputDirectoryParams):
    sources: list[LabelmeSource] = Field(min_length=1, title="输入数据源")
    classes: list[str] = Field(min_length=1, title="类别顺序")
    split: str = Field(default="train", min_length=1, title="输出划分名称")
    unknown_label_policy: Literal["error", "skip"] = Field(default="error", title="未知类别处理")
    include_empty: bool = Field(default=True, title="保留空标注")

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned or len(cleaned) != len(set(cleaned)):
            raise ValueError("类别列表不能为空或重复")
        return cleaned

    @model_validator(mode="after")
    def validate_names_and_output(self) -> LabelmeToYoloParams:
        names = [source.name.strip() for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("来源名称不能重复")
        validate_output_outside(self.output_dir, [source.path for source in self.sources])
        return self
