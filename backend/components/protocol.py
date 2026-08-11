from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from backend.components.manager import ComponentManager, provider_environment

if TYPE_CHECKING:
    from backend.tools.base import TaskContext

PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    provider_version: str
    protocol_version: int
    model_id: str
    model_revision: str
    model_dir: str
    devices: tuple[str, ...]


@dataclass(frozen=True)
class ProviderEmbeddingResult:
    embeddings: dict[Path, np.ndarray]
    errors: dict[Path, str]
    metadata: ProviderMetadata
    device: str
    batch_size: int


class EmbeddingProviderClient:
    def __init__(
        self,
        manager: ComponentManager,
        component_id: str,
        context: TaskContext,
        *,
        startup_timeout: float = 30.0,
    ) -> None:
        self.manager = manager
        self.component_id = component_id
        self.context = context
        self.startup_timeout = startup_timeout
        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[str] = queue.Queue()
        self.reader: threading.Thread | None = None
        self.stderr_lines: deque[str] = deque(maxlen=100)
        self.stderr_reader: threading.Thread | None = None
        self.metadata: ProviderMetadata | None = None

    def __enter__(self) -> EmbeddingProviderClient:
        command = self.manager.command(self.component_id)
        self.process = subprocess.Popen(
            [*command, "--serve-stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=provider_environment(self.manager),
        )
        assert self.process.stdout is not None
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.reader.start()
        self.stderr_reader = threading.Thread(target=self._read_stderr_lines, daemon=True)
        self.stderr_reader.start()
        try:
            hello = self._read_message(self.startup_timeout)
            if hello.get("event") != "ready":
                raise RuntimeError("模型组件未返回 ready 握手")
            protocol_version = int(hello.get("protocol_version", 0))
            if protocol_version != PROTOCOL_VERSION:
                raise RuntimeError(
                    f"模型组件协议不兼容: 需要 {PROTOCOL_VERSION}，收到 {protocol_version}"
                )
            self.metadata = ProviderMetadata(
                provider_id=str(hello["provider_id"]),
                provider_version=str(hello["provider_version"]),
                protocol_version=protocol_version,
                model_id=str(hello["model_id"]),
                model_revision=str(hello["model_revision"]),
                model_dir=str(hello.get("model_dir", "")),
                devices=tuple(str(item) for item in hello.get("devices", [])),
            )
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            try:
                self._write_message({"method": "shutdown"})
                process.wait(timeout=2)
            except (BrokenPipeError, OSError, ValueError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

    def _read_lines(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            self.messages.put(line)

    def _read_stderr_lines(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_lines.append(line.rstrip())

    def _stderr(self) -> str:
        return "\n".join(self.stderr_lines).strip()

    def _read_message(self, timeout: float | None = None) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            self.context.wait_if_paused()
            self.context.raise_if_cancelled()
            if self.process.poll() is not None:
                detail = self._stderr()
                raise RuntimeError(
                    f"模型组件意外退出 ({self.process.returncode})"
                    + (f": {detail}" if detail else "")
                )
            wait = 0.1
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("等待模型组件响应超时")
                wait = min(wait, remaining)
            try:
                line = self.messages.get(timeout=wait)
            except queue.Empty:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("模型组件返回了无效 JSON") from exc
            if not isinstance(message, dict):
                raise RuntimeError("模型组件消息必须是 JSON 对象")
            return message

    def _write_message(self, message: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def embed(
        self,
        paths: list[Path],
        *,
        batch_size: int,
        device: str,
        progress_offset: int = 0,
        progress_total: int | None = None,
    ) -> ProviderEmbeddingResult:
        assert self.metadata is not None
        if device == "cuda" and "cuda" not in self.metadata.devices:
            raise RuntimeError("当前模型组件不支持 CUDA；请使用 CPU 或安装 CUDA Provider")
        requested_device = "cpu" if device == "auto" else device
        self._write_message(
            {
                "method": "embed",
                "paths": [str(path) for path in paths],
                "batch_size": batch_size,
                "device": requested_device,
            }
        )
        embeddings: dict[Path, np.ndarray] = {}
        errors: dict[Path, str] = {}
        actual_batch_size = batch_size
        while True:
            message = self._read_message()
            event = message.get("event")
            if event == "batch":
                actual_batch_size = int(message.get("batch_size", actual_batch_size))
                for item in message.get("items", []):
                    path = Path(str(item["path"]))
                    if item.get("error"):
                        errors[path] = str(item["error"])
                    else:
                        embeddings[path] = np.asarray(item["embedding"], dtype=np.float32)
                completed = len(embeddings) + len(errors)
                self.context.report_progress(
                    progress_offset + completed,
                    progress_total or len(paths),
                    f"正在提取图像特征 · 批大小 {actual_batch_size}",
                    success_count=len(embeddings),
                    failure_count=len(errors),
                )
            elif event == "complete":
                return ProviderEmbeddingResult(
                    embeddings,
                    errors,
                    self.metadata,
                    str(message.get("device", requested_device)),
                    int(message.get("batch_size", actual_batch_size)),
                )
            elif event == "error":
                raise RuntimeError(str(message.get("error") or "模型组件推理失败"))
