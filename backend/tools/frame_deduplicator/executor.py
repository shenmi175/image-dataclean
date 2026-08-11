from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from backend.components import ComponentManager, EmbeddingProviderClient
from backend.tools.base import TaskContext, Tool
from backend.tools.common import (
    IMAGE_SUFFIXES,
    atomic_transfer,
    checkpoint,
    discover_files,
    write_csv,
    write_json,
)
from backend.tools.frame_deduplicator.spec import FrameDeduplicatorParams


@dataclass(frozen=True)
class ImageItem:
    path: Path
    relative: Path
    size_bytes: int
    sha256: str


@dataclass
class Decision:
    item: ImageItem
    status: Literal["kept", "exact_duplicate", "similar", "failed"]
    representative: Path | None = None
    similarity: float | None = None
    action: str = "unchanged"
    error: str = ""


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: dict[Path, np.ndarray]
    errors: dict[Path, str]
    device: str
    batch_size: int
    provider_id: str = "test-provider"
    provider_version: str = "0.0.0"
    model_id: str = "test-model"
    model_revision: str = "test"
    model_dir: str = ""


def natural_key(path: Path | str) -> tuple[object, ...]:
    parts: list[object] = []
    value = path.as_posix() if isinstance(path, Path) else path
    for part in re.split(r"(\d+)", value.casefold()):
        parts.append(int(part) if part.isdigit() else part)
    return tuple(parts)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_sequences(
    items: list[ImageItem], scope: Literal["directory", "global"]
) -> list[list[ImageItem]]:
    if scope == "global":
        return [sorted(items, key=lambda item: natural_key(item.relative))]
    grouped: dict[Path, list[ImageItem]] = defaultdict(list)
    for item in items:
        grouped[item.relative.parent].append(item)
    return [
        sorted(grouped[parent], key=lambda item: natural_key(item.relative.name))
        for parent in sorted(grouped, key=natural_key)
    ]


def unique_embedding_candidates(sequences: list[list[ImageItem]]) -> list[ImageItem]:
    candidates: list[ImageItem] = []
    for sequence in sequences:
        seen_hashes: set[str] = set()
        for item in sequence:
            if not item.sha256 or item.sha256 in seen_hashes:
                continue
            seen_hashes.add(item.sha256)
            candidates.append(item)
    return candidates


def decide_frames(
    sequences: list[list[ImageItem]],
    embeddings: dict[Path, np.ndarray],
    errors: dict[Path, str],
    threshold: float,
) -> list[Decision]:
    decisions: list[Decision] = []
    for sequence in sequences:
        seen_hashes: dict[str, ImageItem] = {}
        representative: ImageItem | None = None
        for item in sequence:
            if item.path in errors:
                decisions.append(Decision(item, "failed", error=errors[item.path]))
                continue
            exact = seen_hashes.get(item.sha256) if item.sha256 else None
            if exact is not None:
                decisions.append(
                    Decision(item, "exact_duplicate", exact.relative, 1.0)
                )
                continue
            embedding = embeddings.get(item.path)
            if embedding is None:
                decisions.append(Decision(item, "failed", error="未生成图像特征"))
                continue
            if item.sha256:
                seen_hashes[item.sha256] = item
            if representative is None:
                representative = item
                decisions.append(Decision(item, "kept", item.relative, 1.0))
                continue
            similarity = float(np.dot(embedding, embeddings[representative.path]))
            if similarity >= threshold:
                decisions.append(
                    Decision(item, "similar", representative.relative, similarity)
                )
            else:
                representative = item
                decisions.append(Decision(item, "kept", item.relative, similarity))
    return decisions


def embed_images(
    items: list[ImageItem],
    batch_size: int,
    requested_device: str,
    context: TaskContext,
    *,
    component_id: str = "dinov3-cpu",
    license_sha256: str | None = None,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> EmbeddingResult:
    manager = ComponentManager()
    descriptor = manager.descriptor(component_id)
    if license_sha256 != descriptor.license.sha256:
        raise RuntimeError("模型许可证尚未接受或版本已变化，请重新创建任务")
    context.log("info", f"检查模型组件: {descriptor.name} {descriptor.version}")
    manager.ensure_installed(
        component_id,
        checkpoint=lambda: checkpoint(context),
        progress=lambda current, total: context.report_progress(
            current,
            total or None,
            "正在下载模型组件",
        ),
    )
    with EmbeddingProviderClient(manager, component_id, context) as client:
        result = client.embed(
            [item.path for item in items],
            batch_size=batch_size,
            device=requested_device,
            progress_offset=progress_offset,
            progress_total=progress_total,
        )
    metadata = result.metadata
    return EmbeddingResult(
        result.embeddings,
        result.errors,
        result.device,
        result.batch_size,
        metadata.provider_id,
        metadata.provider_version,
        metadata.model_id,
        metadata.model_revision,
        metadata.model_dir,
    )


def decision_row(decision: Decision) -> dict[str, Any]:
    return {
        "relative_path": decision.item.relative.as_posix(),
        "status": decision.status,
        "representative_path": (
            decision.representative.as_posix() if decision.representative else ""
        ),
        "similarity": (
            f"{decision.similarity:.6f}" if decision.similarity is not None else ""
        ),
        "sha256": decision.item.sha256,
        "size_bytes": decision.item.size_bytes,
        "action": decision.action,
        "error": decision.error,
    }


REPORT_FIELDS = [
    "relative_path",
    "status",
    "representative_path",
    "similarity",
    "sha256",
    "size_bytes",
    "action",
    "error",
]


class FrameDeduplicatorTool(Tool):
    id = "dinov3-frame-deduplicator"
    name = "DINOv3 视频帧清理"
    category = "数据清理"
    version = "1.0.0"
    description = "使用 DINOv3 动态选择代表帧，清理重复或高度相似的图片。"
    params_model = FrameDeduplicatorParams
    ui_schema = {
        "order": [
            "input_dir",
            "recursive",
            "comparison_scope",
            "operation",
            "confirm_delete",
            "output_dir",
            "similarity_threshold",
            "batch_size",
            "device",
            "embedding_provider",
            "model_license_sha256",
        ],
        "widgets": {
            "input_dir": "directory",
            "output_dir": "directory",
            "comparison_scope": "radio",
            "operation": "radio",
            "device": "radio",
            "embedding_provider": "hidden",
            "model_license_sha256": "hidden",
        },
        "visible_if": {
            "confirm_delete": {"field": "operation", "equals": "delete"},
        },
        "enum_labels": {
            "comparison_scope": {"directory": "各目录内", "global": "全目录"},
            "operation": {"copy": "复制保留帧", "delete": "原地永久删除"},
            "device": {"auto": "自动", "cpu": "CPU", "cuda": "CUDA"},
        },
        "enum_options": {"device": ["auto", "cpu"]},
        "submit_label": "创建视频帧清理任务",
        "notice": (
            "默认复制代表帧且不修改源目录。原地清理会永久删除冗余图片；"
            "首次提交任务前需要阅读并明确接受独立的 DINOv3 License。"
        ),
    }

    def run(
        self, params: FrameDeduplicatorParams, context: TaskContext
    ) -> dict[str, Any]:
        started = time.monotonic()
        root = params.input_dir.expanduser().resolve()
        paths = discover_files(root, IMAGE_SUFFIXES, recursive=params.recursive)
        if not paths:
            raise ValueError("没有找到支持的图片文件")
        output = Path(context.output_path)
        output.mkdir(parents=True, exist_ok=True)
        context.log("info", f"发现 {len(paths)} 张图片，开始计算文件摘要")

        items: list[ImageItem] = []
        hash_errors: dict[Path, str] = {}
        for index, path in enumerate(paths, start=1):
            checkpoint(context)
            try:
                items.append(
                    ImageItem(path, path.relative_to(root), path.stat().st_size, file_sha256(path))
                )
            except OSError as exc:
                hash_errors[path] = str(exc) or exc.__class__.__name__
                items.append(ImageItem(path, path.relative_to(root), 0, ""))
            context.report_progress(index, len(paths) * 3, "正在计算文件摘要")

        sequences = build_sequences(items, params.comparison_scope)
        candidates = unique_embedding_candidates(sequences)
        embedding_result = embed_images(
            candidates,
            params.batch_size,
            params.device,
            context,
            component_id=params.embedding_provider,
            license_sha256=params.model_license_sha256,
            progress_offset=len(paths),
            progress_total=len(paths) * 3,
        )
        errors = {**hash_errors, **embedding_result.errors}
        decisions = decide_frames(
            sequences,
            embedding_result.embeddings,
            errors,
            params.similarity_threshold,
        )

        if params.operation == "delete":
            for decision in decisions:
                decision.action = (
                    "delete_planned"
                    if decision.status in {"exact_duplicate", "similar"}
                    else "unchanged"
                )
            write_csv(
                output / "deletion_plan.csv",
                [decision_row(decision) for decision in decisions],
                REPORT_FIELDS,
            )

        succeeded = failed = 0
        for completed, decision in enumerate(decisions, start=1):
            checkpoint(context)
            try:
                if decision.status == "kept" and params.operation == "copy":
                    target = output / "cleaned" / decision.item.relative
                    atomic_transfer(decision.item.path, target, mode="copy")
                    decision.action = "copied"
                elif decision.status in {"exact_duplicate", "similar"}:
                    if params.operation == "delete":
                        decision.item.path.unlink()
                        decision.action = "deleted"
                    else:
                        decision.action = "omitted"
            except OSError as exc:
                decision.status = "failed"
                decision.error = str(exc) or exc.__class__.__name__
                decision.action = "failed"
            if decision.status == "failed":
                failed += 1
            else:
                succeeded += 1
            context.report_progress(
                len(paths) * 2 + completed,
                len(paths) * 3,
                f"正在应用清理结果: {decision.item.relative}",
                success_count=succeeded,
                failure_count=failed,
            )

        for decision in decisions:
            if decision.status == "failed":
                context.record_failure(str(decision.item.path), decision.error)
        kept = sum(item.status == "kept" for item in decisions)
        exact = sum(item.status == "exact_duplicate" for item in decisions)
        similar = sum(item.status == "similar" for item in decisions)
        failures = sum(item.status == "failed" for item in decisions)
        valid = len(decisions) - failures
        source_bytes = sum(item.item.size_bytes for item in decisions)
        redundant_bytes = sum(
            item.item.size_bytes
            for item in decisions
            if item.status in {"exact_duplicate", "similar"}
        )
        summary = {
            "tool": self.id,
            "provider_id": embedding_result.provider_id,
            "provider_version": embedding_result.provider_version,
            "model_id": embedding_result.model_id,
            "model_revision": embedding_result.model_revision,
            "model_dir": embedding_result.model_dir,
            "input_dir": str(root),
            "recursive": params.recursive,
            "comparison_scope": params.comparison_scope,
            "operation": params.operation,
            "similarity_threshold": params.similarity_threshold,
            "requested_device": params.device,
            "device": embedding_result.device,
            "requested_batch_size": params.batch_size,
            "actual_batch_size": embedding_result.batch_size,
            "scanned": len(paths),
            "valid": valid,
            "kept": kept,
            "exact_duplicates": exact,
            "similar": similar,
            "failures": failures,
            "source_bytes": source_bytes,
            "redundant_bytes": redundant_bytes,
            "reduction_ratio": round(redundant_bytes / source_bytes, 6)
            if source_bytes
            else 0.0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / "summary.json", summary)
        write_csv(
            output / "decisions.csv",
            [decision_row(decision) for decision in decisions],
            REPORT_FIELDS,
        )
        if valid == 0:
            raise RuntimeError("所有图片均处理失败")
        context.report_progress(
            len(paths) * 3,
            len(paths) * 3,
            f"处理完成：保留 {kept}，清理 {exact + similar}，失败 {failures}",
            success_count=valid,
            failure_count=failures,
            force=True,
        )
        return {
            "output_path": str(output),
            "success_count": valid,
            "failure_count": failures,
            "message": f"已保留 {kept} 张，清理 {exact + similar} 张相似帧",
        }
