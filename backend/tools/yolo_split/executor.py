from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.tools.base import TaskCancelled, TaskContext, Tool
from backend.tools.common import (
    IMAGE_SUFFIXES,
    checkpoint,
    find_image,
    read_yolo_classes,
    read_yolo_lines,
    transfer_file,
    validate_yolo_line,
    write_csv,
    write_json,
    write_yolo_yaml,
)
from backend.tools.yolo_split.spec import YoloSplitParams


@dataclass(frozen=True)
class Sample:
    stem: str
    image: Path
    label: Path
    original_split: str


def load_samples(root: Path, split: str) -> list[Sample]:
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    if not image_dir.exists() and not label_dir.exists():
        return []
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise ValueError(f"YOLO {split} 图像/标签目录不完整")
    samples = []
    for label in sorted(label_dir.glob("*.txt")):
        image = find_image(image_dir, label.stem)
        if image is None:
            raise ValueError(f"标签缺少图像: {label}")
        for line in read_yolo_lines(label):
            validate_yolo_line(line, label)
        samples.append(Sample(label.stem, image, label, split))
    image_stems = {
        path.stem
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }
    label_stems = {sample.stem for sample in samples}
    if image_stems != label_stems:
        raise ValueError(f"{split} 存在无标签图像: {sorted(image_stems - label_stems)[:5]}")
    return samples


class YoloSplitTool(Tool):
    id = "yolo-dataset-split"
    name = "YOLO 数据集安全划分"
    category = "数据集处理"
    version = "1.0.0"
    description = "复制 YOLO 数据集并按固定种子安全生成 train/val，绝不修改源目录。"
    params_model = YoloSplitParams
    ui_schema = {
        "order": ["input_dir", "output_dir", "val_ratio", "seed", "existing_val_policy"],
        "widgets": {"input_dir": "directory", "output_dir": "directory"},
        "enum_labels": {
            "existing_val_policy": {
                "preserve": "保留已有 val，不足时补充",
                "resplit": "合并后重新划分",
            }
        },
        "submit_label": "创建 YOLO 划分任务",
        "notice": "只复制到独立任务目录；源数据集不会被移动或改写。",
    }

    def run(self, params: YoloSplitParams, context: TaskContext) -> dict[str, Any]:
        source = params.input_dir.expanduser().resolve()
        classes = read_yolo_classes(source)
        train = load_samples(source, "train")
        existing_val = load_samples(source, "val")
        if not train and not existing_val:
            raise ValueError("train/val 中没有配对样本")
        all_samples = train + existing_val
        stems = [sample.stem for sample in all_samples]
        if len(stems) != len(set(stems)):
            raise ValueError("train 与 val 中存在同名样本，无法安全合并")
        rng = random.Random(params.seed)
        desired_val = round(len(all_samples) * params.val_ratio)
        if params.existing_val_policy == "resplit":
            selected_val = set(rng.sample(stems, desired_val))
        else:
            selected_val = {sample.stem for sample in existing_val}
            supplement = max(0, desired_val - len(selected_val))
            selected_val.update(
                sample.stem for sample in rng.sample(train, min(supplement, len(train)))
            )
        assignments = [
            (sample, "val" if sample.stem in selected_val else "train") for sample in all_samples
        ]
        test_samples = load_samples(source, "test")
        assignments.extend((sample, "test") for sample in test_samples)
        output = Path(context.output_path)
        rows: list[dict[str, Any]] = []
        success = failures = 0
        started = time.monotonic()
        for index, (sample, target_split) in enumerate(assignments, start=1):
            checkpoint(context)
            row = {
                "stem": sample.stem,
                "source_split": sample.original_split,
                "output_split": target_split,
                "status": "failed",
                "error": "",
            }
            try:
                image_target = output / "images" / target_split / sample.image.name
                label_target = output / "labels" / target_split / sample.label.name
                copied = transfer_file(sample.image, image_target, context)
                if copied is None:
                    raise RuntimeError("图像目标冲突已跳过")
                paired_label = label_target.with_name(f"{copied.stem}.txt")
                paired_label.parent.mkdir(parents=True, exist_ok=True)
                paired_label.write_text(sample.label.read_text(encoding="utf-8"), encoding="utf-8")
                success += 1
                row["status"] = "success"
            except TaskCancelled:
                raise
            except Exception as exc:
                failures += 1
                row["error"] = str(exc) or exc.__class__.__name__
                context.record_failure(str(sample.image), row["error"])
            rows.append(row)
            context.report_progress(
                index,
                len(assignments),
                f"正在写入 {target_split}/{sample.image.name}",
                success_count=success,
                failure_count=failures,
            )
        write_yolo_yaml(
            output,
            classes,
            [
                split
                for split in ("train", "val", "test")
                if any(target == split for _, target in assignments)
            ],
        )
        counts = {
            split: sum(target == split for _, target in assignments)
            for split in ("train", "val", "test")
        }
        summary = {
            "tool": self.id,
            "policy": params.existing_val_policy,
            "seed": params.seed,
            "requested_val_ratio": params.val_ratio,
            "actual_val_ratio": counts["val"] / max(len(all_samples), 1),
            "counts": counts,
            "success": success,
            "failures": failures,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / "summary.json", summary)
        write_csv(
            output / "files.csv", rows, ["stem", "source_split", "output_split", "status", "error"]
        )
        if success == 0:
            raise RuntimeError("没有成功写入任何样本")
        return {
            "output_path": str(output),
            "success_count": success,
            "failure_count": failures,
            "message": (
                f"划分完成：train {counts['train']}，val {counts['val']}，test {counts['test']}"
            ),
        }
