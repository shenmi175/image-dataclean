from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel


class TaskCancelled(Exception):
    """Raised by a tool at a cooperative cancellation checkpoint."""


@dataclass(frozen=True)
class ToolCapabilities:
    transfer_modes: tuple[str, ...] = ("copy",)
    supports_parallel: bool = False
    parallel_strategy: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transfer_modes": list(self.transfer_modes),
            "supports_parallel": self.supports_parallel,
            "parallel_strategy": self.parallel_strategy,
        }


class TaskContext(ABC):
    task_id: str
    output_path: str
    parallel_workers: int = 1

    @abstractmethod
    def wait_if_paused(self) -> None: ...

    @abstractmethod
    def raise_if_cancelled(self) -> None: ...

    @abstractmethod
    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
        *,
        success_count: int | None = None,
        failure_count: int | None = None,
        force: bool = False,
    ) -> None: ...

    @abstractmethod
    def log(self, level: str, message: str) -> None: ...

    @abstractmethod
    def record_failure(self, item: str, error: str) -> None: ...

    def request_conflict_resolution(self, source: str, target: str) -> dict[str, str]:
        """Pause the task until the caller resolves an output-path conflict."""
        raise RuntimeError("当前任务上下文不支持交互式冲突处理")


class Tool(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]
    supports_pause: ClassVar[bool] = True
    supports_resume_after_restart: ClassVar[bool] = False
    ui_schema: ClassVar[dict[str, Any]] = {}
    capabilities: ClassVar[ToolCapabilities] = ToolCapabilities()

    @classmethod
    def metadata(cls) -> dict[str, Any]:
        ui_schema = deepcopy(cls.ui_schema)
        if cls.capabilities.supports_parallel:
            order = list(ui_schema.get("order", []))
            if "parallel_workers" not in order:
                order.append("parallel_workers")
            ui_schema["order"] = order
        return {
            "id": cls.id,
            "name": cls.name,
            "category": cls.category,
            "version": cls.version,
            "description": cls.description,
            "status": "available",
            "supports_pause": cls.supports_pause,
            "supports_resume_after_restart": cls.supports_resume_after_restart,
            "params_schema": cls.params_model.model_json_schema(mode="validation"),
            "ui_schema": ui_schema,
            "capabilities": cls.capabilities.as_dict(),
        }

    @abstractmethod
    def run(self, params: BaseModel, context: TaskContext) -> dict[str, Any]: ...
