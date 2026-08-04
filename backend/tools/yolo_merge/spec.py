from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.tools.common import ParallelToolParams, validate_output_outside


class YoloSource(BaseModel):
    name: str = Field(min_length=1, title="来源名称")
    path: Path = Field(title="YOLO 数据集目录")
    class_map: dict[str, str] = Field(default_factory=dict, title="类别映射")

    @field_validator("path")
    @classmethod
    def source_exists(cls, value: Path) -> Path:
        if not value.expanduser().is_dir():
            raise ValueError(f"YOLO 数据集不存在: {value}")
        return value


class YoloMergeParams(ParallelToolParams):
    sources: list[YoloSource] = Field(min_length=1, title="输入数据源")
    output_classes: list[str] = Field(min_length=1, title="输出类别顺序")
    splits: list[str] = Field(
        default_factory=lambda: ["train", "val"], min_length=1, title="合并划分"
    )
    unmapped_policy: Literal["error", "drop"] = Field(default="error", title="未映射类别处理")
    filtered_empty_policy: Literal["drop", "keep"] = Field(default="drop", title="过滤后空标签")

    @field_validator("output_classes", "splits")
    @classmethod
    def unique_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned or len(cleaned) != len(set(cleaned)):
            raise ValueError("列表不能为空或包含重复项")
        return cleaned

    @model_validator(mode="after")
    def validate_sources_and_mapping(self) -> YoloMergeParams:
        names = [source.name.strip() for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("来源名称不能重复")
        allowed = set(self.output_classes)
        invalid = [
            target
            for source in self.sources
            for target in source.class_map.values()
            if target not in allowed
        ]
        if invalid:
            raise ValueError(f"类别映射目标不在输出类别中: {invalid[0]}")
        validate_output_outside(
            self.output_dir, [source.path for source in self.sources], "输入数据集"
        )
        return self
