from __future__ import annotations

import asyncio
import multiprocessing
import queue
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.compat import UTC
from backend.infrastructure.database import Database, utc_now
from backend.scheduler.events import EventBroker
from backend.scheduler.models import TERMINAL_STATUSES, TaskStatus
from backend.scheduler.worker import run_task_worker
from backend.tools.registry import registry


@dataclass
class RunningTask:
    process: multiprocessing.Process
    pause_event: Any
    cancel_event: Any
    message_queue: Any
    resolution_queue: Any
    cancelling_at: float | None = None
    exit_seen_at: float | None = None


class TaskManager:
    def __init__(
        self,
        database: Database,
        broker: EventBroker,
        *,
        max_workers: int,
        cancel_timeout: float = 5.0,
    ) -> None:
        self.database = database
        self.broker = broker
        self.max_workers = max_workers
        self.cancel_timeout = cancel_timeout
        self._context = multiprocessing.get_context("spawn")
        self._running: dict[str, RunningTask] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self.database.initialize()
        stored_workers = self.database.get_setting("max_workers")
        if isinstance(stored_workers, int) and 1 <= stored_workers <= 32:
            self.max_workers = stored_workers
        self.database.mark_interrupted()
        self._stopping = False
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            await self._loop_task
        for task_id, running in list(self._running.items()):
            running.cancel_event.set()
            await asyncio.to_thread(running.process.join, 1.0)
            if running.process.is_alive():
                running.process.terminate()
                await asyncio.to_thread(running.process.join, 2.0)
            task = self.database.get_task(task_id)
            if task and TaskStatus(task["status"]) not in TERMINAL_STATUSES:
                self.database.update_task(
                    task_id,
                    status=TaskStatus.INTERRUPTED,
                    message="应用退出，任务已中断",
                    error_summary="应用在任务运行期间退出",
                    finished_at=utc_now(),
                )
            self._close_running(task_id)

    async def create_task(
        self,
        tool_id: str,
        raw_params: dict[str, Any],
        *,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        tool = registry.get(tool_id)
        params = tool.params_model.model_validate(raw_params)
        serialized = params.model_dump(mode="json")
        task_id = uuid.uuid4().hex
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_root = Path(params.output_dir).expanduser().resolve()
        output_path = output_root / f"{timestamp}_{task_id[:8]}"
        task = self.database.create_task(
            task_id=task_id,
            tool_id=tool_id,
            tool_version=tool.version,
            params=serialized,
            output_path=str(output_path),
            source_task_id=source_task_id,
        )
        await self._publish(task, "task.created")
        return task

    async def pause(self, task_id: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        if task["status"] == TaskStatus.PAUSED:
            return task
        if task["status"] != TaskStatus.RUNNING or task_id not in self._running:
            raise ValueError("只有运行中的任务可以暂停")
        self._running[task_id].pause_event.set()
        self.database.append_event(task_id, "task.pause_requested", "正在安全暂停任务")
        return task

    async def resume(self, task_id: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        if task["status"] == TaskStatus.RUNNING:
            return task
        if task["status"] != TaskStatus.PAUSED or task_id not in self._running:
            raise ValueError("只有已暂停的任务可以恢复")
        if task.get("pending_conflict"):
            raise ValueError("请先处理目标文件冲突")
        self._running[task_id].pause_event.clear()
        return task

    async def cancel(self, task_id: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        status = TaskStatus(task["status"])
        if status in TERMINAL_STATUSES:
            return task
        if status == TaskStatus.PENDING:
            updated = self.database.update_task(
                task_id,
                status=TaskStatus.CANCELLED,
                message="任务已取消",
                finished_at=utc_now(),
            )
            self.database.append_event(task_id, "task.cancelled", "任务已取消")
            await self._publish(updated, "task.updated")
            return updated
        running = self._running.get(task_id)
        if running:
            running.cancel_event.set()
            running.cancelling_at = running.cancelling_at or time.monotonic()
        self.database.abandon_pending_conflict(task_id)
        updated = self.database.update_task(
            task_id,
            status=TaskStatus.CANCELLING,
            message="正在取消任务",
        )
        await self._publish(updated, "task.updated")
        return updated

    async def resolve_conflict(
        self,
        task_id: str,
        conflict_id: str,
        action: str,
        scope: str,
    ) -> dict[str, Any]:
        task = self._require_task(task_id)
        running = self._running.get(task_id)
        if task["status"] != TaskStatus.PAUSED or running is None:
            raise ValueError("只有因冲突暂停的运行中任务可以处理冲突")
        self.database.resolve_conflict(task_id, conflict_id, action, scope)
        running.resolution_queue.put(
            {
                "conflict_id": conflict_id,
                "action": action,
                "scope": scope,
            }
        )
        updated = self.database.update_task(
            task_id,
            status=TaskStatus.RUNNING,
            message="冲突已处理，任务继续运行",
        )
        self.database.append_event(
            task_id,
            "task.conflict_resolved",
            f"目标冲突处理方式: {action} ({scope})",
        )
        await self._publish(updated, "task.updated")
        return updated

    async def retry(self, task_id: str) -> dict[str, Any]:
        source = self._require_task(task_id)
        if TaskStatus(source["status"]) not in TERMINAL_STATUSES:
            raise ValueError("只有已结束的任务可以重试")
        return await self.create_task(
            source["tool_id"],
            source["params"],
            source_task_id=task_id,
        )

    def set_max_workers(self, value: int) -> None:
        if not 1 <= value <= 32:
            raise ValueError("并发任务数必须在 1 到 32 之间")
        self.max_workers = value

    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                async with self._lock:
                    await self._drain_messages()
                    await self._check_processes()
                    await self._schedule_pending()
            except Exception:
                # Keep the scheduler alive; API/logging can still expose individual failures.
                pass
            await asyncio.sleep(0.1)

    async def _schedule_pending(self) -> None:
        slots = self.max_workers - len(self._running)
        if slots <= 0:
            return
        pending = self.database.list_pending(slots)
        for task in pending:
            pause_event = self._context.Event()
            cancel_event = self._context.Event()
            message_queue = self._context.Queue()
            resolution_queue = self._context.Queue()
            process = self._context.Process(
                target=run_task_worker,
                args=(
                    task["id"],
                    task["tool_id"],
                    task["params"],
                    task["output_path"],
                    pause_event,
                    cancel_event,
                    message_queue,
                    resolution_queue,
                ),
                name=f"toolbox-{task['id'][:8]}",
            )
            process.start()
            self._running[task["id"]] = RunningTask(
                process,
                pause_event,
                cancel_event,
                message_queue,
                resolution_queue,
            )
            updated = self.database.update_task(
                task["id"],
                status=TaskStatus.RUNNING,
                message="任务开始执行",
                started_at=utc_now(),
            )
            self.database.append_event(task["id"], "task.started", "任务开始执行")
            await self._publish(updated, "task.updated")

    async def _drain_messages(self) -> None:
        for task_id, running in list(self._running.items()):
            while True:
                try:
                    message = running.message_queue.get_nowait()
                except queue.Empty:
                    break
                await self._handle_message(task_id, message)

    async def _handle_message(self, task_id: str, message: dict[str, Any]) -> None:
        kind = message["kind"]
        if kind == "progress":
            fields = {
                key: value for key, value in message.items() if key != "kind" and value is not None
            }
            task = self.database.update_task(task_id, **fields)
            await self._publish(task, "task.progress")
        elif kind == "state":
            task = self.database.update_task(
                task_id,
                status=message["status"],
                message=message["message"],
            )
            self.database.append_event(task_id, f"task.{message['status']}", message["message"])
            await self._publish(task, "task.updated")
        elif kind == "log":
            self.database.append_event(task_id, "task.log", message["message"], message["level"])
            await self.broker.publish({"type": "task.log", "task_id": task_id, **message})
        elif kind == "failure":
            self.database.add_failure(task_id, message["item"], message["error"])
        elif kind == "conflict":
            conflict = self.database.create_conflict(
                conflict_id=message["conflict_id"],
                task_id=task_id,
                source_path=message["source_path"],
                target_path=message["target_path"],
            )
            task = self.database.update_task(
                task_id,
                status=TaskStatus.PAUSED,
                message="目标文件已存在，请选择处理方式",
            )
            self.database.append_event(
                task_id,
                "task.conflict",
                f"目标已存在: {message['target_path']}",
                "warning",
            )
            await self.broker.publish(
                {"type": "task.conflict", "task_id": task_id, "task": task, "conflict": conflict}
            )
        elif kind == "completed":
            result = message["result"]
            self.database.abandon_pending_conflict(task_id)
            task = self.database.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                message=result.get("message", "任务完成"),
                success_count=result.get("success_count", 0),
                failure_count=result.get("failure_count", 0),
                output_path=result.get("output_path"),
                progress=100.0,
                finished_at=utc_now(),
            )
            self.database.append_event(task_id, "task.completed", task["message"])
            await self._publish(task, "task.updated")
        elif kind == "cancelled":
            self.database.abandon_pending_conflict(task_id)
            task = self.database.update_task(
                task_id,
                status=TaskStatus.CANCELLED,
                message=message["message"],
                finished_at=utc_now(),
            )
            self.database.append_event(task_id, "task.cancelled", message["message"])
            await self._publish(task, "task.updated")
        elif kind == "failed":
            self.database.abandon_pending_conflict(task_id)
            self.database.append_event(task_id, "task.traceback", message["traceback"], "debug")
            task = self.database.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message="任务执行失败",
                error_summary=message["error"],
                finished_at=utc_now(),
            )
            self.database.append_event(task_id, "task.failed", message["error"], "error")
            await self._publish(task, "task.updated")

    async def _check_processes(self) -> None:
        now = time.monotonic()
        for task_id, running in list(self._running.items()):
            task = self.database.get_task(task_id)
            if task is None:
                continue
            if running.cancelling_at and now - running.cancelling_at > self.cancel_timeout:
                if running.process.is_alive():
                    running.process.terminate()
                await asyncio.to_thread(running.process.join, 1.0)
                updated = self.database.update_task(
                    task_id,
                    status=TaskStatus.CANCELLED,
                    message="任务已强制终止，部分输出已保留",
                    error_summary="任务未在取消超时内响应",
                    finished_at=utc_now(),
                )
                await self._publish(updated, "task.updated")
                self._close_running(task_id)
                continue
            if running.process.is_alive():
                continue
            if running.exit_seen_at is None:
                running.exit_seen_at = now
                continue
            if now - running.exit_seen_at < 0.2:
                continue
            await asyncio.to_thread(running.process.join, 0.1)
            task = self.database.get_task(task_id)
            if task and TaskStatus(task["status"]) not in TERMINAL_STATUSES:
                updated = self.database.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Worker 进程异常退出",
                    error_summary=f"Worker exit code: {running.process.exitcode}",
                    finished_at=utc_now(),
                )
                await self._publish(updated, "task.updated")
            self._close_running(task_id)

    def _close_running(self, task_id: str) -> None:
        running = self._running.pop(task_id, None)
        if running:
            running.message_queue.close()
            running.resolution_queue.close()

    def _require_task(self, task_id: str) -> dict[str, Any]:
        task = self.database.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    async def _publish(self, task: dict[str, Any], event_type: str) -> None:
        await self.broker.publish({"type": event_type, "task_id": task["id"], "task": task})
