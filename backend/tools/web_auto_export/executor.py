from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.tools.base import TaskCancelled, TaskContext, Tool
from backend.tools.common import checkpoint, transfer_file, write_csv, write_json
from backend.tools.web_auto_export.coco import build_coco
from backend.tools.web_auto_export.common import (
    annotation_label,
    annotation_path,
    load_annotations,
    split_images,
)
from backend.tools.web_auto_export.labelme import labelme_document
from backend.tools.web_auto_export.spec import WebAutoExportParams


def project_classes(project_json: Path | None) -> list[str]:
    if project_json is None:
        return []
    payload = json.loads(project_json.read_text(encoding="utf-8"))
    return [str(item) for item in payload.get("project", {}).get("classes", [])]


class WebAutoExportTool(Tool):
    id = "web-auto-export"
    name = "web-auto 标注导出"
    category = "标注转换"
    version = "1.0.0"
    description = "将 web-auto UUID5 多边形标注导出为 Labelme 或 COCO 数据集。"
    params_model = WebAutoExportParams
    ui_schema = {
        "order": [
            "image_dir",
            "annotation_dir",
            "project_json",
            "output_dir",
            "output_format",
            "splits",
            "classes",
            "copy_images",
            "embed_image_data",
            "include_all",
            "strict_missing",
        ],
        "widgets": {
            "image_dir": "directory",
            "annotation_dir": "directory",
            "project_json": "file",
            "output_dir": "directory",
            "splits": "string-list",
            "classes": "string-list",
        },
        "file_filters": {"project_json": [".json"]},
        "visible_if": {
            "embed_image_data": {"field": "output_format", "equals": "labelme"},
            "include_all": {"field": "output_format", "equals": "coco"},
        },
        "enum_labels": {"output_format": {"labelme": "Labelme", "coco": "COCO"}},
        "submit_label": "创建 web-auto 导出任务",
        "notice": "仅支持当前 web-auto JSON 结构及 UUID5 相对路径标注 ID。",
    }

    def run(self, params: WebAutoExportParams, context: TaskContext) -> dict[str, Any]:
        image_root = params.image_dir.expanduser().resolve()
        annotation_root = params.annotation_dir.expanduser().resolve()
        output = Path(context.output_path)
        all_items: list[tuple[str, Path, str, Path, list[dict[str, Any]]]] = []
        for split in params.splits:
            for image in split_images(image_root, split):
                relative = image.relative_to(image_root).as_posix()
                ann_path = annotation_path(annotation_root, relative)
                if params.strict_missing and not ann_path.is_file():
                    raise FileNotFoundError(f"图像缺少标注: {relative}")
                item = (split, image, relative, ann_path, load_annotations(ann_path))
                all_items.append(item)
        if not all_items:
            raise ValueError("没有找到待导出的图像")
        classes = list(dict.fromkeys(params.classes or project_classes(params.project_json)))
        if not classes:
            classes = list(
                dict.fromkeys(
                    annotation_label(annotation)
                    for _, _, _, _, source_annotations in all_items
                    for annotation in source_annotations
                    if annotation_label(annotation)
                )
            )
        if not classes and params.output_format == "coco":
            raise ValueError("无法确定类别顺序")

        rows: list[dict[str, Any]] = []
        success = failures = missing = skipped_shapes = 0
        started = time.monotonic()
        coco_groups: dict[str, list[tuple[Path, str, list[dict[str, Any]]]]] = {}
        for index, (split, image, relative, ann_path, source_annotations) in enumerate(
            all_items, start=1
        ):
            checkpoint(context)
            row = {
                "source": str(image),
                "annotation": str(ann_path),
                "output": "",
                "status": "failed",
                "error": "",
            }
            try:
                if not ann_path.exists():
                    missing += 1
                copied: Path | None = None
                if params.copy_images:
                    target = (
                        output
                        / ("labelme" if params.output_format == "labelme" else "images")
                        / relative
                    )
                    copied = transfer_file(image, target, context)
                    if copied is None:
                        raise RuntimeError("目标冲突已跳过")
                if params.output_format == "labelme":
                    json_target = (output / "labelme" / relative).with_suffix(".json")
                    document, skipped = labelme_document(
                        image,
                        json_target,
                        source_annotations,
                        copied_image=copied,
                        embed_image_data=params.embed_image_data,
                    )
                    write_json(json_target, document)
                    skipped_shapes += skipped
                    row["output"] = str(json_target.relative_to(output))
                else:
                    coco_file_name = (
                        copied.relative_to(output / "images").as_posix()
                        if copied is not None
                        else relative
                    )
                    coco_groups.setdefault(split, []).append(
                        (image, coco_file_name, source_annotations)
                    )
                    row["output"] = (
                        f"annotations/instances_{'root' if split == '.' else split}.json"
                    )
                success += 1
                row["status"] = "success"
            except TaskCancelled:
                raise
            except Exception as exc:
                failures += 1
                row["error"] = str(exc) or exc.__class__.__name__
                context.record_failure(str(image), row["error"])
            rows.append(row)
            context.report_progress(
                index,
                len(all_items),
                f"正在导出 {relative}",
                success_count=success,
                failure_count=failures,
            )

        if params.output_format == "coco":
            for split, items in coco_groups.items():
                document, skipped = build_coco(items, classes)
                skipped_shapes += skipped
                write_json(
                    output / "annotations" / f"instances_{'root' if split == '.' else split}.json",
                    document,
                )
            if params.include_all:
                document, skipped = build_coco(
                    [item for items in coco_groups.values() for item in items], classes
                )
                skipped_shapes += skipped
                write_json(output / "annotations" / "instances_all.json", document)
        summary = {
            "tool": self.id,
            "format": params.output_format,
            "classes": classes,
            "images": len(all_items),
            "success": success,
            "failures": failures,
            "missing_annotations": missing,
            "skipped_shapes": skipped_shapes,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / "summary.json", summary)
        write_csv(output / "files.csv", rows, ["source", "annotation", "output", "status", "error"])
        if success == 0:
            raise RuntimeError("没有成功导出任何图像")
        return {
            "output_path": str(output),
            "success_count": success,
            "failure_count": failures,
            "message": f"已导出 {success} 张图像为 {params.output_format.upper()}",
        }
