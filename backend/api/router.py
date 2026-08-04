from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import StreamingResponse

from backend.core.compat import UTC
from backend.core.settings import available_cpu_count, default_workers, recommended_parallel_workers
from backend.infrastructure.system import open_path, select_directory, select_files
from backend.scheduler.models import TERMINAL_STATUSES, TaskStatus
from backend.tools.registry import registry

api_router = APIRouter()


class CreateTaskRequest(BaseModel):
    tool_id: str
    params: dict[str, Any]


class OpenPathRequest(BaseModel):
    path: str = Field(min_length=1)


class ResolveConflictRequest(BaseModel):
    conflict_id: str = Field(min_length=1)
    action: Literal["skip", "overwrite", "rename"]
    scope: Literal["current", "remaining"]


class SelectFilesRequest(BaseModel):
    title: str = "选择文件"
    extensions: list[str] = Field(default_factory=list)
    multiple: bool = True


class VideoFramesDefaults(BaseModel):
    recursive: bool = True
    frame_interval: int = Field(default=10, ge=1, le=1_000_000)
    resize: bool = True
    width: int = Field(default=640, ge=1, le=32768)
    height: int = Field(default=640, ge=1, le=32768)
    resize_mode: Literal["letterbox", "direct"] = "letterbox"


class AppSettingsUpdate(BaseModel):
    max_workers: int = Field(ge=1, le=32)
    parallel_workers: int = Field(default=0, ge=0, le=32)
    default_output_dir: str | None = None
    video_frames: VideoFramesDefaults = Field(default_factory=VideoFramesDefaults)


SETTINGS_KEYS = [
    "max_workers",
    "parallel_workers",
    "default_output_dir",
    "tool_defaults.video-frames",
]


def manager(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.task_manager


@api_router.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "automation-toolbox",
        "time": datetime.now(UTC).isoformat(),
        "scheduler": hasattr(request.app.state, "task_manager"),
    }


@api_router.get("/config", tags=["system"])
async def public_config(request: Request) -> dict[str, int]:
    return {
        "max_workers": manager(request).max_workers,
        "recommended_workers": default_workers(),
        "parallel_workers": manager(request).parallel_workers,
        "default_parallel_workers": request.app.state.default_parallel_workers,
        "recommended_parallel_workers": recommended_parallel_workers(manager(request).max_workers),
        "cpu_count": available_cpu_count(),
    }


def resolved_app_settings(request: Request) -> dict[str, Any]:
    database = manager(request).database
    raw_video_defaults = database.get_setting("tool_defaults.video-frames", {})
    try:
        video_defaults = VideoFramesDefaults.model_validate(raw_video_defaults)
    except ValidationError:
        video_defaults = VideoFramesDefaults()
    output_dir = database.get_setting("default_output_dir")
    return {
        "max_workers": manager(request).max_workers,
        "default_max_workers": request.app.state.default_max_workers,
        "recommended_workers": default_workers(),
        "parallel_workers": manager(request).parallel_workers,
        "default_parallel_workers": request.app.state.default_parallel_workers,
        "recommended_parallel_workers": recommended_parallel_workers(manager(request).max_workers),
        "cpu_count": available_cpu_count(),
        "default_output_dir": output_dir if isinstance(output_dir, str) else None,
        "video_frames": video_defaults.model_dump(mode="json"),
    }


@api_router.get("/settings", tags=["settings"])
async def get_settings(request: Request) -> dict[str, Any]:
    return resolved_app_settings(request)


@api_router.put("/settings", tags=["settings"])
async def update_settings(payload: AppSettingsUpdate, request: Request) -> dict[str, Any]:
    output_dir: str | None = None
    if payload.default_output_dir and payload.default_output_dir.strip():
        target = Path(payload.default_output_dir).expanduser().resolve()
        if target.exists() and not target.is_dir():
            raise HTTPException(status_code=422, detail="默认输出路径不是目录")
        output_dir = str(target)
    manager(request).database.set_settings(
        {
            "max_workers": payload.max_workers,
            "parallel_workers": payload.parallel_workers,
            "default_output_dir": output_dir,
            "tool_defaults.video-frames": payload.video_frames.model_dump(mode="json"),
        }
    )
    manager(request).set_max_workers(payload.max_workers)
    manager(request).set_parallel_workers(payload.parallel_workers)
    return resolved_app_settings(request)


@api_router.post("/settings/reset", tags=["settings"])
async def reset_settings(request: Request) -> dict[str, Any]:
    manager(request).database.clear_settings(SETTINGS_KEYS)
    manager(request).set_max_workers(request.app.state.default_max_workers)
    manager(request).set_parallel_workers(request.app.state.default_parallel_workers)
    return resolved_app_settings(request)


@api_router.get("/tools", tags=["tools"])
async def list_tools() -> list[dict[str, Any]]:
    return [tool.metadata() for tool in registry.list()]


@api_router.get("/tools/{tool_id}", tags=["tools"])
async def get_tool(tool_id: str) -> dict[str, Any]:
    try:
        return registry.get(tool_id).metadata()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/tasks", status_code=201, tags=["tasks"])
async def create_task(payload: CreateTaskRequest, request: Request) -> dict[str, Any]:
    try:
        return await manager(request).create_task(payload.tool_id, payload.params)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc


@api_router.get("/tasks", tags=["tasks"])
async def list_tasks(
    request: Request,
    status: TaskStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return manager(request).database.list_tasks(
        status=status.value if status else None,
        limit=limit,
        offset=offset,
    )


@api_router.get("/tasks/active", tags=["tasks"])
async def active_tasks(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return manager(request).database.list_active(limit=limit)


@api_router.get("/tasks/history", tags=["tasks"])
async def task_history(
    request: Request,
    status: Annotated[list[TaskStatus] | None, Query()] = None,
    tool_id: str | None = None,
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    selected_statuses = status or []
    invalid = [item for item in selected_statuses if item not in TERMINAL_STATUSES]
    if invalid:
        raise HTTPException(status_code=422, detail="执行历史只接受已结束状态")
    items, total, counts = manager(request).database.list_history(
        statuses=[item.value for item in selected_statuses] or None,
        tool_id=tool_id,
        query=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "counts": counts}


@api_router.get("/tasks/{task_id}", tags=["tasks"])
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    task = manager(request).database.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    task["failures"] = manager(request).database.get_failures(task_id)
    return task


def delete_task_output(task: dict[str, Any]) -> bool:
    raw_path = task.get("output_path")
    if not raw_path:
        return False
    target = Path(raw_path).expanduser()
    if not target.exists():
        return False
    if target.is_symlink() or not target.is_dir():
        raise ValueError("任务输出路径不是可安全清理的目录")
    resolved = target.resolve()
    forbidden = {Path("/"), Path.home().resolve()}
    expected_suffix = f"_{task['id'][:8]}"
    if resolved in forbidden or not resolved.name.endswith(expected_suffix):
        raise ValueError("拒绝删除非本任务生成的目录")
    shutil.rmtree(resolved)
    return True


@api_router.delete("/tasks/{task_id}", tags=["tasks"])
async def delete_task(
    task_id: str,
    request: Request,
    delete_output: bool = False,
) -> dict[str, bool]:
    task = manager(request).database.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if TaskStatus(task["status"]) not in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="活动任务不能删除")
    output_deleted = False
    if delete_output:
        try:
            output_deleted = await asyncio.to_thread(delete_task_output, task)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    manager(request).database.delete_task(task_id)
    return {"deleted": True, "output_deleted": output_deleted}


async def task_action(task_id: str, request: Request, action: str) -> dict[str, Any]:
    try:
        return await getattr(manager(request), action)(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api_router.post("/tasks/{task_id}/pause", tags=["tasks"])
async def pause_task(task_id: str, request: Request) -> dict[str, Any]:
    return await task_action(task_id, request, "pause")


@api_router.post("/tasks/{task_id}/resume", tags=["tasks"])
async def resume_task(task_id: str, request: Request) -> dict[str, Any]:
    return await task_action(task_id, request, "resume")


@api_router.post("/tasks/{task_id}/cancel", tags=["tasks"])
async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    return await task_action(task_id, request, "cancel")


@api_router.post("/tasks/{task_id}/retry", status_code=201, tags=["tasks"])
async def retry_task(task_id: str, request: Request) -> dict[str, Any]:
    return await task_action(task_id, request, "retry")


@api_router.post("/tasks/{task_id}/resolve-conflict", tags=["tasks"])
async def resolve_task_conflict(
    task_id: str,
    payload: ResolveConflictRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await manager(request).resolve_conflict(
            task_id,
            payload.conflict_id,
            payload.action,
            payload.scope,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api_router.get("/tasks/{task_id}/logs", tags=["tasks"])
async def task_logs(
    task_id: str,
    request: Request,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    if manager(request).database.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return manager(request).database.get_logs(task_id, after_id=after_id, limit=limit)


@api_router.post("/dialogs/select-directory", tags=["system"])
async def choose_directory() -> dict[str, str | None]:
    try:
        return {"path": await asyncio.to_thread(select_directory)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法打开目录选择器: {exc}") from exc


@api_router.post("/dialogs/select-files", tags=["system"])
async def choose_files(payload: SelectFilesRequest | None = None) -> dict[str, list[str]]:
    options = payload or SelectFilesRequest()
    try:
        return {
            "paths": await asyncio.to_thread(
                select_files,
                options.title,
                options.extensions,
                multiple=options.multiple,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法打开文件选择器: {exc}") from exc


@api_router.post(
    "/system/open-path",
    status_code=204,
    response_class=Response,
    response_model=None,
    tags=["system"],
)
async def reveal_path(payload: OpenPathRequest) -> Response:
    try:
        await asyncio.to_thread(open_path, payload.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="路径不存在") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法打开文件管理器: {exc}") from exc
    return Response(status_code=204)


@api_router.websocket("/events")
async def events(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    if not settings.auth_disabled:
        supplied_token = websocket.query_params.get("token")
        if supplied_token != settings.session_token:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    broker = websocket.app.state.event_broker
    try:
        async with broker.subscribe() as event_queue:
            while True:
                event = await event_queue.get()
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return


@api_router.get("/events/stream", tags=["tasks"])
async def event_stream(
    request: Request,
    token: str | None = Query(default=None),
) -> StreamingResponse:
    settings = request.app.state.settings
    if not settings.auth_disabled and token != settings.session_token:
        raise HTTPException(status_code=401, detail="未授权")

    return StreamingResponse(
        stream_event_messages(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def stream_event_messages(
    request: Request, heartbeat_seconds: float = 15
) -> AsyncIterator[str]:
    broker = request.app.state.event_broker
    try:
        async with broker.subscribe() as event_queue:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(), timeout=heartbeat_seconds
                    )
                except asyncio.TimeoutError:  # noqa: UP041 - distinct on Python 3.10
                    yield ": keepalive\n\n"
                    continue
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"data: {payload}\n\n"
    except asyncio.CancelledError:
        # StreamingResponse cancels the iterator when the browser closes or reconnects.
        return
