from __future__ import annotations

import hashlib
import math
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from backend.tools.annotation_visualizer.parsers import (
    VisualSample,
    coco_samples,
    labelme_samples,
    yolo_samples,
)
from backend.tools.annotation_visualizer.spec import AnnotationVisualizerParams
from backend.tools.base import TaskContext, Tool, ToolCapabilities
from backend.tools.common import parallel_map, safe_name, write_csv, write_json


def color_for(label: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    return tuple(60 + value % 176 for value in digest[:3])  # type: ignore[return-value]


def render(
    sample: VisualSample, alpha: float, allowed: set[str] | None
) -> tuple[Image.Image, Counter[str]]:
    image = Image.open(sample.image).convert("RGB")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    counts: Counter[str] = Counter()
    for polygon in sample.polygons:
        if allowed is not None and polygon.label not in allowed:
            continue
        color = color_for(polygon.label)
        draw.polygon(
            polygon.points, fill=(*color, round(alpha * 255)), outline=(*color, 255), width=2
        )
        if polygon.points:
            draw.text(
                polygon.points[0],
                polygon.label,
                fill=(*color, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
            )
        counts[polygon.label] += 1
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), counts


def save_mosaic(images: list[Path], target: Path, columns: int) -> None:
    tiles = []
    for path in images:
        tile = Image.open(path).convert("RGB")
        tile.thumbnail((320, 240), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (320, 240), (24, 24, 24))
        canvas.paste(tile, ((320 - tile.width) // 2, (240 - tile.height) // 2))
        tiles.append(canvas)
    rows = math.ceil(len(tiles) / columns)
    mosaic = Image.new("RGB", (columns * 320, rows * 240), (24, 24, 24))
    for index, tile in enumerate(tiles):
        mosaic.paste(tile, ((index % columns) * 320, (index // columns) * 240))
    target.parent.mkdir(parents=True, exist_ok=True)
    mosaic.save(target, quality=92)


class AnnotationVisualizerTool(Tool):
    id = "annotation-visualizer"
    name = "标注可视化与抽样"
    category = "数据集检查"
    version = "1.0.0"
    description = "可视化 Labelme、YOLO segmentation 或 COCO polygon 标注并生成分页拼图。"
    params_model = AnnotationVisualizerParams
    capabilities = ToolCapabilities(supports_parallel=True, parallel_strategy="thread")
    ui_schema = {
        "order": [
            "annotation_format",
            "input_dir",
            "annotation_file",
            "data_yaml",
            "classes",
            "class_filter",
            "output_dir",
            "sample_mode",
            "limit",
            "seed",
            "alpha",
            "mosaic_columns",
            "mosaic_page_size",
        ],
        "widgets": {
            "input_dir": "directory",
            "annotation_file": "file",
            "data_yaml": "file",
            "classes": "string-list",
            "class_filter": "string-list",
            "output_dir": "directory",
        },
        "file_filters": {"annotation_file": [".json"], "data_yaml": [".yaml", ".yml"]},
        "visible_if": {
            "annotation_file": {"field": "annotation_format", "equals": "coco"},
            "data_yaml": {"field": "annotation_format", "equals": "yolo"},
            "classes": {"field": "annotation_format", "equals": "yolo"},
        },
        "enum_labels": {
            "annotation_format": {"labelme": "Labelme", "yolo": "YOLO 分割", "coco": "COCO"},
            "sample_mode": {"first": "按顺序", "random": "随机抽样"},
        },
        "submit_label": "创建标注可视化任务",
        "notice": "首版支持多边形标注，不包含语义 mask、RLE 或 SUNRGBD Parquet。",
    }

    def run(self, params: AnnotationVisualizerParams, context: TaskContext) -> dict[str, Any]:
        root = params.input_dir.expanduser().resolve()
        if params.annotation_format == "labelme":
            samples = labelme_samples(root)
        elif params.annotation_format == "yolo":
            samples = yolo_samples(root, params.data_yaml, params.classes)
        else:
            assert params.annotation_file is not None
            samples = coco_samples(root, params.annotation_file.expanduser().resolve())
        if not samples:
            raise ValueError("没有发现可视化样本")
        if params.sample_mode == "random":
            samples = random.Random(params.seed).sample(samples, min(params.limit, len(samples)))
        else:
            samples = samples[: params.limit]
        output = Path(context.output_path)
        image_dir = output / "images"
        rows: list[dict[str, Any] | None] = [None] * len(samples)
        rendered_by_index: dict[int, Path] = {}
        total_classes: Counter[str] = Counter()
        success = failures = 0
        allowed = set(params.class_filter) if params.class_filter else None
        started = time.monotonic()
        def process(job: tuple[int, VisualSample]) -> tuple[Path, Counter[str]]:
            index, sample = job
            target = image_dir / f"{index:04d}_{safe_name(Path(sample.key).stem)}.jpg"
            if not sample.image.is_file():
                raise FileNotFoundError(f"图像不存在: {sample.image}")
            visual, counts = render(sample, params.alpha, allowed)
            target.parent.mkdir(parents=True, exist_ok=True)
            visual.save(target, quality=94)
            return target, counts

        jobs = list(enumerate(samples, start=1))
        for completed, result in enumerate(parallel_map(jobs, process, context), start=1):
            index, sample = result.item
            row = {
                "sample": sample.key,
                "source_image": str(sample.image),
                "output": "",
                "status": "failed",
                "classes": "",
                "error": "",
            }
            if result.error is None and result.value is not None:
                target, counts = result.value
                rendered_by_index[index] = target
                total_classes.update(counts)
                success += 1
                row.update(
                    output=str(target.relative_to(output)),
                    status="success",
                    classes=json_counts(counts),
                )
            else:
                failures += 1
                assert result.error is not None
                row["error"] = str(result.error) or result.error.__class__.__name__
                context.record_failure(str(sample.image), row["error"])
            rows[index - 1] = row
            context.report_progress(
                completed,
                len(samples),
                f"正在渲染 {sample.key}",
                success_count=success,
                failure_count=failures,
            )
        rendered_paths = [
            rendered_by_index[index] for index, _ in jobs if index in rendered_by_index
        ]
        for start in range(0, len(rendered_paths), params.mosaic_page_size):
            page = rendered_paths[start : start + params.mosaic_page_size]
            save_mosaic(
                page,
                output / f"mosaic_{start // params.mosaic_page_size + 1:02d}.jpg",
                params.mosaic_columns,
            )
        summary = {
            "tool": self.id,
            "format": params.annotation_format,
            "selected": len(samples),
            "success": success,
            "failures": failures,
            "class_instances": dict(total_classes),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "parallel_workers": context.parallel_workers,
        }
        write_json(output / "summary.json", summary)
        write_csv(
            output / "selected_samples.csv",
            [row for row in rows if row is not None],
            ["sample", "source_image", "output", "status", "classes", "error"],
        )
        if success == 0:
            raise RuntimeError("没有成功生成任何可视化结果")
        return {
            "output_path": str(output),
            "success_count": success,
            "failure_count": failures,
            "message": (
                f"已生成 {success} 张可视化及 {math.ceil(success / params.mosaic_page_size)} 页拼图"
            ),
        }


def json_counts(counts: Counter[str]) -> str:
    return ";".join(f"{name}:{count}" for name, count in sorted(counts.items()))
