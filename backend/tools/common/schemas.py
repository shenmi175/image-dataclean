from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class OutputDirectoryParams(BaseModel):
    output_dir: Path = Field(title="输出目录")

    @field_validator("output_dir")
    @classmethod
    def output_must_be_directory(cls, value: Path) -> Path:
        if value.expanduser().exists() and not value.expanduser().is_dir():
            raise ValueError(f"输出路径不是目录: {value}")
        return value
