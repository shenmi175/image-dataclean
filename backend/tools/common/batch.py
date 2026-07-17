from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.tools.base import TaskContext


def checkpoint(context: TaskContext) -> None:
    context.raise_if_cancelled()
    context.wait_if_paused()


@dataclass
class BatchProgress:
    context: TaskContext
    total: int | None
    unit: str = "项"
    success_count: int = 0
    failure_count: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def checkpoint(self) -> None:
        checkpoint(self.context)

    def success(self) -> None:
        self.success_count += 1

    def failure(self, item: str, error: BaseException | str) -> None:
        self.failure_count += 1
        message = (
            str(error) or error.__class__.__name__
            if isinstance(error, BaseException)
            else error
        )
        self.context.record_failure(item, message)

    def report(self, current: int, message: str = "", *, force: bool = False) -> None:
        elapsed = max(time.monotonic() - self.started_at, 0.001)
        suffix = f" · {current / elapsed:.1f} {self.unit}/秒" if current else ""
        self.context.report_progress(
            current,
            self.total,
            f"{message}{suffix}",
            success_count=self.success_count,
            failure_count=self.failure_count,
            force=force,
        )
