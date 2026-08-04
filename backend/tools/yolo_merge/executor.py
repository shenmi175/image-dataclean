from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.tools.base import TaskContext, Tool, ToolCapabilities
from backend.tools.common import (
    IMAGE_SUFFIXES,
    find_image,
    parallel_map,
    read_yolo_classes,
    read_yolo_lines,
    safe_name,
    transfer_file,
    validate_yolo_line,
    write_csv,
    write_json,
    write_yolo_yaml,
)
from backend.tools.yolo_merge.spec import YoloMergeParams, YoloSource


def mapped_class(
    source_id: int,
    source_classes: list[str],
    source: YoloSource,
    output_ids: dict[str, int],
) -> int | None:
    if source_id >= len(source_classes):
        raise ValueError(f"来源类别 ID 超出 data.yaml names: {source_id}")
    source_name = source_classes[source_id]
    target_name = source.class_map.get(
        str(source_id), source.class_map.get(source_name, source_name)
    )
    return output_ids.get(target_name)


class YoloMergeTool(Tool):
    id = "yolo-dataset-merge"
    name = "YOLO 合并与类别映射"
    category = "数据集处理"
    version = "1.0.0"
    description = "合并多个 YOLO segmentation 数据集并按名称或 ID 重映射类别。"
    params_model = YoloMergeParams
    capabilities = ToolCapabilities(supports_parallel=True, parallel_strategy="thread")
    ui_schema = {
        "order": [
            "sources",
            "output_classes",
            "output_dir",
            "splits",
            "unmapped_policy",
            "filtered_empty_policy",
        ],
        "widgets": {
            "sources": "object-list",
            "sources[].path": "directory",
            "sources[].class_map": "key-value",
            "output_classes": "string-list",
            "output_dir": "directory",
            "splits": "string-list",
        },
        "enum_labels": {
            "unmapped_policy": {"error": "记录为错误", "drop": "丢弃未映射类别"},
            "filtered_empty_policy": {"drop": "丢弃样本", "keep": "保留为空标注"},
        },
        "submit_label": "创建 YOLO 合并任务",
        "notice": "类别映射可使用来源类别名称或 ID；空映射默认按同名类别合并。",
    }

    def run(self, params: YoloMergeParams, context: TaskContext) -> dict[str, Any]:
        output = Path(context.output_path)
        output_ids = {name: index for index, name in enumerate(params.output_classes)}
        items: list[tuple[YoloSource, list[str], str, Path, Path]] = []
        for source in params.sources:
            root = source.path.expanduser().resolve()
            source_classes = read_yolo_classes(root)
            for split in params.splits:
                label_dir = root / "labels" / split
                image_dir = root / "images" / split
                if not label_dir.exists() and not image_dir.exists():
                    continue
                if not label_dir.is_dir() or not image_dir.is_dir():
                    raise ValueError(f"来源 {source.name} 的 {split} 目录不完整")
                labels = sorted(label_dir.glob("*.txt"))
                image_stems = {
                    path.stem
                    for path in image_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                }
                label_stems = {label.stem for label in labels}
                if image_stems != label_stems:
                    raise ValueError(
                        f"来源 {source.name}/{split} 图像标签不配对: "
                        f"缺标签={sorted(image_stems - label_stems)[:3]} "
                        f"缺图像={sorted(label_stems - image_stems)[:3]}"
                    )
                for label in labels:
                    image = find_image(image_dir, label.stem)
                    if image is None:
                        raise ValueError(f"标签缺少图像: {label}")
                    items.append((source, source_classes, split, image, label))
        if not items:
            raise ValueError("输入数据源没有可合并样本")
        rows: list[dict[str, Any] | None] = [None] * len(items)
        success = failures = dropped_samples = dropped_lines = 0
        started = time.monotonic()
        def process(
            item: tuple[YoloSource, list[str], str, Path, Path]
        ) -> tuple[str, str, int]:
            source, source_classes, split, image, label = item
            output_stem = f"{safe_name(source.name)}__{safe_name(label.stem)}"
            local_dropped_lines = 0
            source_lines = read_yolo_lines(label)
            target_lines = []
            for line in source_lines:
                class_id, _ = validate_yolo_line(line, label)
                target_id = mapped_class(class_id, source_classes, source, output_ids)
                if target_id is None:
                    if params.unmapped_policy == "error":
                        raise ValueError(f"未映射类别: {source_classes[class_id]}")
                    local_dropped_lines += 1
                    continue
                target_lines.append(f"{target_id} {line.split(maxsplit=1)[1]}")
            if source_lines and not target_lines and params.filtered_empty_policy == "drop":
                return "dropped_empty", output_stem, local_dropped_lines
            image_target = output / "images" / split / f"{output_stem}{image.suffix.lower()}"
            label_target = output / "labels" / split / f"{output_stem}.txt"
            copied = transfer_file(image, image_target, context)
            if copied is None:
                raise RuntimeError("目标冲突已跳过")
            paired_label = label_target.with_name(f"{copied.stem}.txt")
            paired_label.parent.mkdir(parents=True, exist_ok=True)
            paired_label.write_text(
                "\n".join(target_lines) + ("\n" if target_lines else ""), encoding="utf-8"
            )
            return "success", copied.stem, local_dropped_lines

        for completed, result in enumerate(parallel_map(items, process, context), start=1):
            source, _source_classes, split, image, label = result.item
            default_stem = f"{safe_name(source.name)}__{safe_name(label.stem)}"
            row = {
                "source": source.name,
                "source_image": str(image),
                "source_label": str(label),
                "split": split,
                "output_stem": default_stem,
                "status": "failed",
                "dropped_lines": 0,
                "error": "",
            }
            if result.error is None and result.value is not None:
                status, output_stem, local_dropped_lines = result.value
                dropped_lines += local_dropped_lines
                row["dropped_lines"] = local_dropped_lines
                row["output_stem"] = output_stem
                row["status"] = status
                if status == "dropped_empty":
                    dropped_samples += 1
                else:
                    success += 1
            else:
                failures += 1
                assert result.error is not None
                row["error"] = str(result.error) or result.error.__class__.__name__
                context.record_failure(str(label), row["error"])
            rows[result.index] = row
            context.report_progress(
                completed,
                len(items),
                f"正在合并 {source.name}/{split}/{image.name}",
                success_count=success,
                failure_count=failures,
            )
        used_splits = [
            split
            for split in params.splits
            if any(
                row is not None and row["split"] == split and row["status"] == "success"
                for row in rows
            )
        ]
        write_yolo_yaml(output, params.output_classes, used_splits)
        summary = {
            "tool": self.id,
            "sources": [source.name for source in params.sources],
            "classes": params.output_classes,
            "input_samples": len(items),
            "success": success,
            "failures": failures,
            "dropped_samples": dropped_samples,
            "dropped_lines": dropped_lines,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "parallel_workers": context.parallel_workers,
        }
        write_json(output / "summary.json", summary)
        write_csv(
            output / "manifest.csv",
            [row for row in rows if row is not None],
            [
                "source",
                "source_image",
                "source_label",
                "split",
                "output_stem",
                "status",
                "dropped_lines",
                "error",
            ],
        )
        if success == 0:
            raise RuntimeError("没有成功合并任何样本")
        return {
            "output_path": str(output),
            "success_count": success,
            "failure_count": failures,
            "message": f"已合并 {success} 个样本，丢弃 {dropped_samples} 个过滤后空样本",
        }
