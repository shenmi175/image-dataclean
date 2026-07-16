from __future__ import annotations

import time
from multiprocessing.synchronize import Event
from typing import Any

from backend.tools.base import TaskCancelled, TaskContext


class WorkerTaskContext(TaskContext):
    def __init__(
        self,
        task_id: str,
        output_path: str,
        pause_event: Event,
        cancel_event: Event,
        message_queue: Any,
    ) -> None:
        self.task_id = task_id
        self.output_path = output_path
        self._pause_event = pause_event
        self._cancel_event = cancel_event
        self._queue = message_queue
        self._paused_reported = False
        self._last_progress_at = 0.0
        self._last_percent: float | None = None
        self._started_at = time.monotonic()

    def wait_if_paused(self) -> None:
        while self._pause_event.is_set():
            self.raise_if_cancelled()
            if not self._paused_reported:
                self._send({"kind": "state", "status": "paused", "message": "任务已暂停"})
                self._paused_reported = True
            time.sleep(0.05)
        if self._paused_reported:
            self._send({"kind": "state", "status": "running", "message": "任务已恢复"})
            self._paused_reported = False

    def raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise TaskCancelled("任务已取消")

    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
        *,
        success_count: int | None = None,
        failure_count: int | None = None,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        percent = min(current / total * 100, 100.0) if total and total > 0 else None
        changed_one_percent = (
            percent is not None
            and (self._last_percent is None or abs(percent - self._last_percent) >= 1.0)
        )
        if not force and now - self._last_progress_at < 0.5 and not changed_one_percent:
            return
        self._last_progress_at = now
        self._last_percent = percent
        self._send(
            {
                "kind": "progress",
                "current": current,
                "total": total,
                "progress": percent,
                "message": message,
                "speed": current / max(now - self._started_at, 0.001),
                "success_count": success_count,
                "failure_count": failure_count,
            }
        )

    def log(self, level: str, message: str) -> None:
        self._send({"kind": "log", "level": level, "message": message})

    def record_failure(self, item: str, error: str) -> None:
        self._send({"kind": "failure", "item": item, "error": error})
        self.log("error", f"{item}: {error}")

    def _send(self, message: dict[str, Any]) -> None:
        self._queue.put(message)
