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


def test_task_conflict_is_persisted_and_resolved(tmp_path: Path) -> None:
    database = Database(tmp_path / "toolbox.sqlite3")
    database.initialize()
    database.create_task(
        task_id="conflict-task",
        tool_id="image-rgb-ir-classifier",
        tool_version="1.0.0",
        params={},
        output_path="/tmp/result",
    )

    conflict = database.create_conflict(
        conflict_id="conflict-1",
        task_id="conflict-task",
        source_path="/tmp/source.jpg",
        target_path="/tmp/result/source_rgb.jpg",
    )

    assert conflict["status"] == "pending"
    assert database.get_task("conflict-task")["pending_conflict"]["id"] == "conflict-1"
    resolved = database.resolve_conflict("conflict-task", "conflict-1", "rename", "remaining")
    assert resolved["action"] == "rename"
    assert resolved["scope"] == "remaining"
    assert database.get_task("conflict-task")["pending_conflict"] is None
