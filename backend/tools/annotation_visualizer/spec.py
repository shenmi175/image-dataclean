from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.tools.common import ParallelToolParams, validate_output_outside


class AnnotationVisualizerParams(ParallelToolParams):
    annotation_format: Literal["labelme", "yolo", "coco"] = Field(title="标注格式")
    input_dir: Path = Field(title="图像/数据集目录")
    annotation_file: Path | None = Field(default=None, title="COCO 标注 JSON")
    data_yaml: Path | None = Field(default=None, title="YOLO data.yaml")
    classes: list[str] = Field(default_factory=list, title="YOLO 类别（可选）")
    class_filter: list[str] = Field(default_factory=list, title="仅显示类别（可选）")
    sample_mode: Literal["first", "random"] = Field(default="random", title="抽样方式")
    limit: int = Field(default=100, ge=1, le=10000, title="最多样本数")
    seed: int = Field(default=42, title="随机种子")
    alpha: float = Field(default=0.5, gt=0.0, le=1.0, title="填充透明度")
    mosaic_columns: int = Field(default=5, ge=1, le=20, title="拼图列数")
    mosaic_page_size: int = Field(default=20, ge=1, le=200, title="每页数量")

    @model_validator(mode="after")
    def validate_paths(self) -> AnnotationVisualizerParams:
        if not self.input_dir.expanduser().is_dir():
            raise ValueError(f"输入目录不存在: {self.input_dir}")
        if self.annotation_format == "coco" and (
            self.annotation_file is None or not self.annotation_file.expanduser().is_file()
        ):
            raise ValueError("COCO 格式必须选择标注 JSON")
        if self.data_yaml is not None and not self.data_yaml.expanduser().is_file():
            raise ValueError(f"data.yaml 不存在: {self.data_yaml}")
        validate_output_outside(self.output_dir, [self.input_dir])
        return self
