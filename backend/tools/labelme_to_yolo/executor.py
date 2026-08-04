from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from backend.tools.base import TaskContext, Tool, ToolCapabilities
from backend.tools.common import (
    IMAGE_SUFFIXES,
    parallel_map,
    safe_name,
    transfer_file,
    write_csv,
    write_json,
    write_yolo_yaml,
)
from backend.tools.labelme_to_yolo.spec import LabelmeSource, LabelmeToYoloParams


def image_for_json(json_path: Path, data: dict[str, Any]) -> Path:
    raw = data.get("imagePath")
    if raw:
        candidate = (json_path.parent / str(raw)).resolve()
        if candidate.is_file():
            return candidate
    for suffix in IMAGE_SUFFIXES:
        candidate = json_path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"找不到标注对应图像: {json_path}")


def points_for_shape(shape: dict[str, Any]) -> list[list[float]] | None:
    raw = shape.get("points")
    if not isinstance(raw, list):
        return None
    points = [[float(point[0]), float(point[1])] for point in raw if len(point) >= 2]
    if shape.get("shape_type") == "rectangle" and len(points) == 2:
        (x1, y1), (x2, y2) = points
        points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return points if len(points) >= 3 else None


def yolo_lines(
    data: dict[str, Any], image: Path, classes: dict[str, int], skip_unknown: bool
) -> tuple[list[str], int, int]:
    width = int(data.get("imageWidth") or 0)
    height = int(data.get("imageHeight") or 0)
    if width <= 0 or height <= 0:
        with Image.open(image) as opened:
            width, height = opened.size
    lines: list[str] = []
    skipped = 0
    unknown = 0
    for shape in data.get("shapes") or []:
        label = str(shape.get("label") or "").strip()
        if label not in classes:
            unknown += 1
            if skip_unknown:
                continue
            raise ValueError(f"未知类别 {label!r}")
        points = points_for_shape(shape)
        if points is None:
            skipped += 1
            continue
        coords: list[float] = []
        for x, y in points:
            coords.extend([min(1.0, max(0.0, x / width)), min(1.0, max(0.0, y / height))])
        lines.append(f"{classes[label]} " + " ".join(f"{value:.6f}" for value in coords))
    return lines, skipped, unknown


class LabelmeToYoloTool(Tool):
    id = "labelme-to-yolo-seg"
    name = "Labelme 转 YOLO 分割"
    category = "标注转换"
    version = "1.0.0"
    description = "将一个或多个 Labelme 多边形目录转换为标准 YOLO segmentation 数据集。"
    params_model = LabelmeToYoloParams
    capabilities = ToolCapabilities(supports_parallel=True, parallel_strategy="thread")
    ui_schema = {
        "order": [
            "sources",
            "classes",
            "output_dir",
            "split",
            "unknown_label_policy",
            "include_empty",
        ],
        "widgets": {
            "sources": "object-list",
            "sources[].path": "directory",
            "classes": "string-list",
            "output_dir": "directory",
        },
        "submit_label": "创建 Labelme 转 YOLO 任务",
        "notice": "类别顺序决定 YOLO 类别 ID；所有源图像会复制到独立任务目录。",
        "enum_labels": {"unknown_label_policy": {"error": "记录为错误", "skip": "跳过未知形状"}},
    }

    def run(self, params: LabelmeToYoloParams, context: TaskContext) -> dict[str, Any]:
        output = Path(context.output_path)
        image_output = output / "images" / params.split
        label_output = output / "labels" / params.split
        image_output.mkdir(parents=True, exist_ok=True)
        label_output.mkdir(parents=True, exist_ok=True)
        class_ids = {name: index for index, name in enumerate(params.classes)}
        items = [
            (source, path, path.relative_to(source.path.expanduser().resolve()))
            for source in params.sources
            for path in sorted(source.path.expanduser().resolve().rglob("*.json"))
        ]
        if not items:
            raise ValueError("没有找到 Labelme JSON 文件")
        rows: list[dict[str, Any] | None] = [None] * len(items)
        success = failures = shapes = skipped_shapes = unknown_shapes = 0
        started = time.monotonic()
        def process(
            item: tuple[LabelmeSource, Path, Path]
        ) -> tuple[str, str, int, int, int]:
            source, json_path, relative = item
            data = json.loads(json_path.read_text(encoding="utf-8"))
            image = image_for_json(json_path, data)
            lines, skipped, unknown = yolo_lines(
                data, image, class_ids, params.unknown_label_policy == "skip"
            )
            if not lines and not params.include_empty:
                return "skipped_empty", "", 0, skipped, unknown
            stem = "__".join(
                [safe_name(source.name), *map(safe_name, relative.with_suffix("").parts)]
            )
            image_target = image_output / f"{stem}{image.suffix.lower()}"
            copied = transfer_file(image, image_target, context)
            if copied is None:
                raise RuntimeError("目标冲突已跳过")
            label_target = label_output / f"{copied.stem}.txt"
            label_target.write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            return "success", str(label_target.relative_to(output)), len(lines), skipped, unknown

        for completed, result in enumerate(parallel_map(items, process, context), start=1):
            _source, json_path, relative = result.item
            row: dict[str, Any] = {
                "source": str(json_path),
                "output": "",
                "status": "failed",
                "error": "",
            }
            if result.error is None and result.value is not None:
                status, output_name, line_count, skipped, unknown = result.value
                skipped_shapes += skipped
                unknown_shapes += unknown
                shapes += line_count
                row.update(output=output_name, status=status)
                if status == "success":
                    success += 1
            else:
                failures += 1
                assert result.error is not None
                row["error"] = str(result.error) or result.error.__class__.__name__
                context.record_failure(str(json_path), row["error"])
            rows[result.index] = row
            context.report_progress(
                completed,
                len(items),
                f"正在转换 {relative}",
                success_count=success,
                failure_count=failures,
            )
        write_yolo_yaml(output, params.classes, [params.split])
        summary = {
            "tool": self.id,
            "files": len(items),
            "success": success,
            "failures": failures,
            "shapes": shapes,
            "skipped_shapes": skipped_shapes,
            "unknown_shapes": unknown_shapes,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "parallel_workers": context.parallel_workers,
        }
        write_json(output / "summary.json", summary)
        write_csv(
            output / "files.csv",
            [row for row in rows if row is not None],
            ["source", "output", "status", "error"],
        )
        if success == 0:
            raise RuntimeError("没有成功转换任何 Labelme 标注")
        return {
            "output_path": str(output),
            "success_count": success,
            "failure_count": failures,
            "message": f"已转换 {success} 份标注，共 {shapes} 个多边形",
        }
