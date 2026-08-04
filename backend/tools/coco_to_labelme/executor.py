from __future__ import annotations

import base64
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.tools.base import TaskContext, Tool, ToolCapabilities
from backend.tools.coco_to_labelme.spec import CocoToLabelmeParams
from backend.tools.common import (
    parallel_map,
    safe_relative_path,
    transfer_file,
    write_csv,
    write_json,
)


def polygons(segmentation: Any) -> list[list[list[float]]]:
    if not isinstance(segmentation, list):
        return []
    result = []
    for coords in segmentation:
        if not isinstance(coords, list) or len(coords) < 6 or len(coords) % 2:
            continue
        result.append(
            [[float(coords[index]), float(coords[index + 1])] for index in range(0, len(coords), 2)]
        )
    return result


class CocoToLabelmeTool(Tool):
    id = "coco-to-labelme"
    name = "COCO 转 Labelme"
    category = "标注转换"
    version = "1.0.0"
    description = "将 COCO polygon segmentation 标注转换为 Labelme JSON。"
    params_model = CocoToLabelmeParams
    capabilities = ToolCapabilities(supports_parallel=True, parallel_strategy="thread")
    ui_schema = {
        "order": [
            "coco_json",
            "image_dir",
            "output_dir",
            "copy_images",
            "embed_image_data",
            "unsupported_policy",
        ],
        "widgets": {"coco_json": "file", "image_dir": "directory", "output_dir": "directory"},
        "file_filters": {"coco_json": [".json"]},
        "enum_labels": {"unsupported_policy": {"skip": "跳过并记录", "error": "记录为错误"}},
        "submit_label": "创建 COCO 转 Labelme 任务",
        "notice": "支持 COCO polygon；RLE segmentation 首版不解码。",
    }

    def run(self, params: CocoToLabelmeParams, context: TaskContext) -> dict[str, Any]:
        payload = json.loads(params.coco_json.read_text(encoding="utf-8"))
        categories = {int(item["id"]): str(item["name"]) for item in payload.get("categories", [])}
        annotations: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in payload.get("annotations", []):
            annotations[int(annotation["image_id"])].append(annotation)
        images = list(payload.get("images", []))
        if not images:
            raise ValueError("COCO JSON 中没有图像记录")
        image_root = params.image_dir.expanduser().resolve()
        output = Path(context.output_path) / "labelme"
        rows: list[dict[str, Any] | None] = [None] * len(images)
        success = failures = skipped = shape_count = 0
        started = time.monotonic()
        def process(image: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
            relative = safe_relative_path(str(image["file_name"]))
            source = image_root / relative
            json_target = (output / relative).with_suffix(".json")
            row = {
                "source": str(source),
                "output": str(json_target),
                "status": "failed",
                "shapes": 0,
                "error": "",
            }
            if not source.is_file():
                raise FileNotFoundError(f"图像不存在: {source}")
            copied: Path | None = None
            if params.copy_images:
                copied = transfer_file(source, output / relative, context)
                if copied is None:
                    raise RuntimeError("目标冲突已跳过")
            shapes = []
            local_skipped = 0
            for annotation in annotations.get(int(image["id"]), []):
                label = categories.get(int(annotation["category_id"]))
                extracted = polygons(annotation.get("segmentation"))
                if not label or not extracted:
                    local_skipped += 1
                    if params.unsupported_policy == "error":
                        raise ValueError(f"不支持的 annotation id={annotation.get('id')}")
                    continue
                for points in extracted:
                    shapes.append(
                        {
                            "label": label,
                            "points": points,
                            "group_id": annotation.get("id"),
                            "description": "",
                            "shape_type": "polygon",
                            "flags": {},
                            "mask": None,
                        }
                    )
            image_path = (
                copied.name
                if copied
                else Path(os.path.relpath(source, json_target.parent)).as_posix()
            )
            document = {
                "version": "5.8.3",
                "flags": {},
                "shapes": shapes,
                "imagePath": image_path,
                "imageData": base64.b64encode(source.read_bytes()).decode("ascii")
                if params.embed_image_data
                else None,
                "imageHeight": int(image["height"]),
                "imageWidth": int(image["width"]),
            }
            write_json(json_target, document)
            row.update(
                status="success",
                shapes=len(shapes),
                output=str(json_target.relative_to(output.parent)),
            )
            return row, len(shapes), local_skipped

        for completed, result in enumerate(parallel_map(images, process, context), start=1):
            image = result.item
            relative = safe_relative_path(str(image["file_name"]))
            source = image_root / relative
            if result.error is None and result.value is not None:
                row, local_shapes, local_skipped = result.value
                shape_count += local_shapes
                skipped += local_skipped
                success += 1
            else:
                failures += 1
                assert result.error is not None
                row = {
                    "source": str(source),
                    "output": str((output / relative).with_suffix(".json")),
                    "status": "failed",
                    "shapes": 0,
                    "error": str(result.error) or result.error.__class__.__name__,
                }
                context.record_failure(str(source), row["error"])
            rows[result.index] = row
            context.report_progress(
                completed,
                len(images),
                f"正在转换 {relative}",
                success_count=success,
                failure_count=failures,
            )
        summary = {
            "tool": self.id,
            "images": len(images),
            "success": success,
            "failures": failures,
            "shapes": shape_count,
            "unsupported_annotations": skipped,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "parallel_workers": context.parallel_workers,
        }
        write_json(output.parent / "summary.json", summary)
        write_csv(
            output.parent / "files.csv",
            [row for row in rows if row is not None],
            ["source", "output", "status", "shapes", "error"],
        )
        if success == 0:
            raise RuntimeError("没有成功转换任何 COCO 图像")
        return {
            "output_path": str(output.parent),
            "success_count": success,
            "failure_count": failures,
            "message": f"已转换 {success} 张图像、{shape_count} 个多边形",
        }
