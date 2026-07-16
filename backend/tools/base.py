from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel


class TaskCancelled(Exception):
    """Raised by a tool at a cooperative cancellation checkpoint."""


class TaskContext(ABC):
    task_id: str
    output_path: str

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

    @classmethod
    def metadata(cls) -> dict[str, Any]:
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
            "ui_schema": cls.ui_schema,
        }

    @abstractmethod
    def run(self, params: BaseModel, context: TaskContext) -> dict[str, Any]: ...
