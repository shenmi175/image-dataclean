import asyncio
import queue
import threading
from pathlib import Path
from unittest.mock import Mock

import backend.scheduler.manager as manager_module
from backend.infrastructure.database import Database
from backend.scheduler.events import EventBroker
from backend.scheduler.manager import RunningTask, TaskManager


def test_manager_pauses_and_resumes_worker_for_conflict(tmp_path: Path) -> None:
    database = Database(tmp_path / "toolbox.sqlite3")
    database.initialize()
    database.create_task(
        task_id="task-with-conflict",
        tool_id="image-rgb-ir-classifier",
        tool_version="1.0.0",
        params={},
        output_path=str(tmp_path / "output"),
    )
    database.update_task("task-with-conflict", status="running")
    manager = TaskManager(database, EventBroker(), max_workers=1)
    resolutions: queue.Queue = queue.Queue()
    manager._running["task-with-conflict"] = RunningTask(
        process=Mock(),
        pause_event=threading.Event(),
        cancel_event=threading.Event(),
        message_queue=queue.Queue(),
        resolution_queue=resolutions,
    )

    async def exercise() -> None:
        await manager._handle_message(
            "task-with-conflict",
            {
                "kind": "conflict",
                "conflict_id": "conflict-id",
                "source_path": "/source/photo.jpg",
                "target_path": "/output/photo_rgb.jpg",
            },
        )
        paused = database.get_task("task-with-conflict")
        assert paused is not None
        assert paused["status"] == "paused"
        assert paused["pending_conflict"]["id"] == "conflict-id"

        resumed = await manager.resolve_conflict(
            "task-with-conflict", "conflict-id", "rename", "remaining"
        )
        assert resumed["status"] == "running"
        assert resumed["pending_conflict"] is None

    asyncio.run(exercise())
    assert resolutions.get_nowait() == {
        "conflict_id": "conflict-id",
        "action": "rename",
        "scope": "remaining",
    }


def test_parallel_worker_budget_uses_auto_global_and_task_override(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(manager_module, "available_cpu_count", lambda: 12)
    monkeypatch.setattr(
        manager_module,
        "recommended_parallel_workers",
        lambda max_workers: max(1, 12 // max_workers),
    )
    manager = TaskManager(
        Database(tmp_path / "parallel.sqlite3"),
        EventBroker(),
        max_workers=4,
        parallel_workers=0,
    )

    assert manager.effective_parallel_workers({"parallel_workers": 0}) == 3
    manager.set_parallel_workers(5)
    assert manager.effective_parallel_workers({"parallel_workers": 0}) == 5
    assert manager.effective_parallel_workers({"parallel_workers": 7}) == 7
