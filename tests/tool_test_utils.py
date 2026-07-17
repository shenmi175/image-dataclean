from pathlib import Path

from backend.tools.base import TaskCancelled, TaskContext


class RecordingContext(TaskContext):
    def __init__(self, output: Path) -> None:
        self.task_id = "dataset-tool-test"
        self.output_path = str(output)
        self.progress: list[tuple[int, int | None]] = []
        self.failures: list[tuple[str, str]] = []
        self.logs: list[str] = []
        self.cancelled = False

    def wait_if_paused(self) -> None:
        return

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled

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
        self.progress.append((current, total))

    def log(self, level: str, message: str) -> None:
        self.logs.append(message)

    def record_failure(self, item: str, error: str) -> None:
        self.failures.append((item, error))

    def request_conflict_resolution(self, source: str, target: str) -> dict[str, str]:
        return {"action": "rename", "scope": "current"}
