from __future__ import annotations

from backend.core.compat import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"



TERMINAL_STATUSES = {
    TaskStatus.CANCELLED,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.INTERRUPTED,
}
