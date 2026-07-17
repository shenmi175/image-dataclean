from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from backend.tools.base import TaskCancelled, TaskContext, Tool, ToolCapabilities
from backend.tools.common import (
    IMAGE_SUFFIXES,
    BatchProgress,
    discover_files,
    transfer_file,
    write_json,
)
from backend.tools.image_classifier.spec import ImageClassifierParams

ImageLabel = Literal["rgb", "ir"]


@dataclass(frozen=True)
class PixelFeatures:
    gray_ratio: float
    mean_channel_spread: float
    p95_channel_spread: float


def pixel_features(rgb: np.ndarray, tolerance: int = 2) -> PixelFeatures:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"期望 HxWx3 RGB 图像，实际形状为 {rgb.shape}")
    if tolerance < 0:
        raise ValueError("通道差容差不能为负数")
    pixels = rgb.astype(np.int16, copy=False)
    spread = pixels.max(axis=2) - pixels.min(axis=2)
    return PixelFeatures(
        gray_ratio=float((spread <= tolerance).mean()),
        mean_channel_spread=float(spread.mean()),
        p95_channel_spread=float(np.percentile(spread, 95)),
    )


def classify_pixels(
    rgb: np.ndarray, threshold: float = 0.90, tolerance: int = 2
) -> tuple[ImageLabel, PixelFeatures]:
    features = pixel_features(rgb, tolerance)
    return ("ir" if features.gray_ratio >= threshold else "rgb"), features


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def discover_images(params: ImageClassifierParams) -> list[tuple[Path, Path]]:
    root = params.input_dir.expanduser().resolve()
    return [
        (path, path.relative_to(root))
        for path in discover_files(root, IMAGE_SUFFIXES, recursive=params.recursive)
    ]


def suffixed_name(path: Path, label: ImageLabel) -> str:
    return f"{path.stem}_{label}{path.suffix}"


def output_relative_path(
    relative: Path,
    label: ImageLabel,
    layout: Literal["all-suffixed", "leaf-suffixed", "category-root"],
) -> Path:
    parents = list(relative.parent.parts) if relative.parent != Path(".") else []
    if layout == "all-suffixed":
        parents = [f"{part}_{label}" for part in parents]
    elif layout == "leaf-suffixed" and parents:
        parents[-1] = f"{parents[-1]}_{label}"
    elif layout == "category-root":
        parents.insert(0, label)
    return Path(*parents, suffixed_name(relative, label))


class ImageClassifierTool(Tool):
    id = "image-rgb-ir-classifier"
    name = "RGB / 红外候选分类"
    category = "图像处理"
    version = "1.0.0"
    description = "根据像素通道差异区分 RGB 与灰度/红外候选图像，并保持目录结构输出。"
    params_model = ImageClassifierParams
    capabilities = ToolCapabilities(transfer_modes=("copy", "move"))
    ui_schema = {
        "order": [
            "input_dir",
            "output_dir",
            "recursive",
            "operation",
            "output_category",
            "layout",
            "threshold",
            "tolerance",
        ],
        "widgets": {"input_dir": "directory", "output_dir": "directory", "operation": "radio"},
        "submit_label": "创建图像分类任务",
        "notice": "灰度图会作为红外候选输出；默认复制源文件，输出位于独立任务目录。",
        "enum_labels": {
            "operation": {"copy": "复制", "move": "移动"},
            "output_category": {"all": "全部", "rgb": "仅 RGB", "ir": "仅红外"},
            "layout": {
                "all-suffixed": "逐级添加后缀",
                "leaf-suffixed": "只改末级目录",
                "category-root": "类别顶层目录",
            },
        },
    }

    def run(self, params: ImageClassifierParams, context: TaskContext) -> dict[str, Any]:
        images = discover_images(params)
        if not images:
            raise ValueError("没有找到支持的图像文件")

        output_root = Path(context.output_path)
        output_root.mkdir(parents=True, exist_ok=True)
        context.log("info", f"发现 {len(images)} 张图像")
        progress = BatchProgress(context, len(images), unit="张")
        labels = {"rgb": 0, "ir": 0}
        skipped = 0

        for index, (source, relative) in enumerate(images, start=1):
            progress.checkpoint()
            try:
                label, _features = classify_pixels(
                    load_rgb(source), params.threshold, params.tolerance
                )
                if params.output_category != "all" and label != params.output_category:
                    skipped += 1
                    continue
                target = output_root / output_relative_path(relative, label, params.layout)
                placed = transfer_file(source, target, context, mode=params.operation)
                if placed is None:
                    raise RuntimeError(f"目标已存在，已跳过: {target}")
                progress.success()
                labels[label] += 1
            except TaskCancelled:
                raise
            except Exception as exc:
                progress.failure(str(source), exc)
            finally:
                progress.report(index, f"正在处理 {relative}")

        if progress.success_count == 0 and skipped == len(images):
            raise RuntimeError("没有找到符合输出类别的图像")
        if progress.success_count == 0:
            raise RuntimeError("所有图像均处理失败")
        progress.report(
            len(images),
            f"处理完成：RGB {labels['rgb']} 张，红外候选 {labels['ir']} 张",
            force=True,
        )
        write_json(output_root / "summary.json", {
            "tool": self.id,
            "operation": params.operation,
            "output_category": params.output_category,
            "rgb": labels["rgb"],
            "ir": labels["ir"],
            "skipped": skipped,
            "success": progress.success_count,
            "failures": progress.failure_count,
        })
        return {
            "output_path": str(output_root),
            "success_count": progress.success_count,
            "failure_count": progress.failure_count,
            "message": (
                f"已分类 {progress.success_count} 张："
                f"RGB {labels['rgb']}，红外候选 {labels['ir']}，跳过 {skipped}"
            ),
        }
