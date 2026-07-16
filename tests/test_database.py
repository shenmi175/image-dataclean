from pathlib import Path

from backend.infrastructure.database import Database
from backend.scheduler.models import TaskStatus


def test_task_persistence_and_interrupted_recovery(tmp_path: Path) -> None:
    database = Database(tmp_path / "toolbox.sqlite3")
    database.initialize()
    task = database.create_task(
        task_id="task-1",
        tool_id="video-frames",
        tool_version="1.0.0",
        params={"input_files": ["video.avi"], "output_dir": "/tmp"},
        output_path="/tmp/result",
    )
    assert task["status"] == TaskStatus.PENDING

    running = database.update_task("task-1", status=TaskStatus.RUNNING, current=12, total=20)
    assert running["revision"] > task["revision"]
    assert database.mark_interrupted() == 1

    recovered = database.get_task("task-1")
    assert recovered is not None
    assert recovered["status"] == TaskStatus.INTERRUPTED


def test_pending_tasks_are_fifo(tmp_path: Path) -> None:
    database = Database(tmp_path / "toolbox.sqlite3")
    database.initialize()
    for task_id in ("first", "second", "third"):
        database.create_task(
            task_id=task_id,
            tool_id="video-frames",
            tool_version="1.0.0",
            params={},
            output_path=f"/tmp/{task_id}",
        )

    assert [task["id"] for task in database.list_pending(2)] == ["first", "second"]
