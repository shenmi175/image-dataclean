import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.router import api_router, stream_event_messages
from backend.app import FRONTEND_DIST, create_app
from backend.core.settings import Settings
from backend.scheduler.models import TaskStatus
from backend.tools.registry import registry
from backend.tools.video_frames import VideoFramesParams


def _test_client(app: object) -> TestClient:
    # The default asyncio selector loop can lose BlockingPortal wakeups under
    # constrained Linux builders. Production already ships uvloop via uvicorn.
    return TestClient(app, backend_options={"use_uvloop": True})  # type: ignore[arg-type]


def test_required_api_routes_are_registered() -> None:
    paths = set(create_app().openapi()["paths"])
    assert {
        "/api/health",
        "/api/tools",
        "/api/tasks",
        "/api/tasks/{task_id}/pause",
        "/api/tasks/{task_id}/resume",
        "/api/tasks/{task_id}/cancel",
        "/api/tasks/{task_id}/retry",
        "/api/tasks/{task_id}/resolve-conflict",
        "/api/tasks/active",
        "/api/tasks/history",
        "/api/settings",
        "/api/settings/reset",
        "/api/components",
        "/api/components/{component_id}/accept-license",
        "/api/events/stream",
    } <= paths
    assert "/events" in {route.path for route in api_router.routes}


def test_component_license_must_be_accepted_before_task_creation(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        component_dir=tmp_path / "components",
        model_dir=tmp_path / "models",
    )
    source = tmp_path / "images"
    source.mkdir()
    params = {"input_dir": str(source), "output_dir": str(tmp_path / "output")}
    with _test_client(create_app(settings)) as client:
        components = client.get("/api/components").json()
        assert components[0]["id"] == "dinov3-cpu"
        assert components[0]["license_accepted"] is False

        rejected = client.post(
            "/api/tasks",
            json={"tool_id": "dinov3-frame-deduplicator", "params": params},
        )
        assert rejected.status_code == 409

        stale = client.post(
            "/api/components/dinov3-cpu/accept-license",
            json={"accepted": True, "license_sha256": "0" * 64},
        )
        assert stale.status_code == 409

        accepted = client.post(
            "/api/components/dinov3-cpu/accept-license",
            json={
                "accepted": True,
                "license_sha256": components[0]["license"]["sha256"],
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["license_accepted"] is True

        refreshed = client.get("/api/components").json()
        assert refreshed[0]["license_accepted"] is True


def test_video_tool_is_discoverable() -> None:
    tools = [tool.metadata() for tool in registry.list()]
    assert {tool["id"] for tool in tools} == {
        "annotation-visualizer",
        "coco-to-labelme",
        "dinov3-frame-deduplicator",
        "image-rgb-ir-classifier",
        "labelme-to-yolo-seg",
        "video-frames",
        "web-auto-export",
        "yolo-dataset-merge",
        "yolo-dataset-split",
    }
    assert all("params_schema" in tool for tool in tools)
    capabilities = {tool["id"]: tool["capabilities"] for tool in tools}
    assert capabilities["image-rgb-ir-classifier"]["transfer_modes"] == ["copy", "move"]
    assert capabilities["yolo-dataset-split"]["transfer_modes"] == ["copy"]
    video_tool = next(tool for tool in tools if tool["id"] == "video-frames")
    assert video_tool["ui_schema"]["order"][0] == "input_path"
    assert "input_files" not in video_tool["ui_schema"]["order"]
    assert "input_dir" not in video_tool["ui_schema"]["order"]


def test_event_stream_keeps_idle_connection_alive_and_delivers_events() -> None:
    from backend.scheduler.events import EventBroker

    class FakeRequest:
        def __init__(self) -> None:
            self.app = SimpleNamespace(state=SimpleNamespace(event_broker=EventBroker()))

        async def is_disconnected(self) -> bool:
            return False

    async def exercise() -> None:
        request = FakeRequest()
        messages = stream_event_messages(request, heartbeat_seconds=0.001)  # type: ignore[arg-type]
        assert await messages.__anext__() == ": connected\n\n"
        assert await messages.__anext__() == ": keepalive\n\n"
        await request.app.state.event_broker.publish({"type": "test", "task_id": "1"})
        assert await messages.__anext__() == 'data: {"type":"test","task_id":"1"}\n\n'
        await messages.aclose()

    asyncio.run(exercise())


def test_video_params_require_a_source() -> None:
    try:
        VideoFramesParams.model_validate({"output_dir": "/tmp"})
    except ValueError as error:
        assert "请选择一个视频文件或视频目录" in str(error)
    else:
        raise AssertionError("source validation did not run")


def test_retry_keeps_legacy_video_source_params(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path / "logs", max_workers=1)
    video = tmp_path / "legacy.avi"
    video.write_bytes(b"legacy task source")
    output_dir = tmp_path / "outputs"
    with _test_client(create_app(settings)) as client:
        database = client.app.state.database
        database.create_task(
            task_id="legacy-video-task",
            tool_id="video-frames",
            tool_version="1.0.0",
            params={
                "input_files": [str(video)],
                "input_dir": None,
                "output_dir": str(output_dir),
            },
            output_path=str(tmp_path / "legacy_result"),
            status=TaskStatus.FAILED,
        )

        response = client.post("/api/tasks/legacy-video-task/retry")

        assert response.status_code == 201
        retried = response.json()
        assert retried["source_task_id"] == "legacy-video-task"
        assert retried["params"]["input_path"] is None
        assert retried["params"]["input_files"] == [str(video)]


def test_built_frontend_contains_application_title() -> None:
    index = Path(FRONTEND_DIST) / "index.html"
    assert index.is_file()
    assert "自动化工具箱" in index.read_text(encoding="utf-8")


def test_websocket_accepts_query_token(tmp_path: Path) -> None:
    settings = Settings(
        auth_disabled=False,
        session_token="test-session-token",
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
    )
    with _test_client(create_app(settings)) as client:
        with client.websocket_connect("/api/events?token=test-session-token"):
            pass


def test_websocket_rejects_invalid_query_token(tmp_path: Path) -> None:
    settings = Settings(
        auth_disabled=False,
        session_token="test-session-token",
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
    )
    with _test_client(create_app(settings)) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("/api/events?token=wrong-token"):
                pass
    assert error.value.code == 4401


def test_event_stream_rejects_invalid_query_token(tmp_path: Path) -> None:
    settings = Settings(
        auth_disabled=False,
        session_token="test-session-token",
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
    )
    with _test_client(create_app(settings)) as client:
        response = client.get("/api/events/stream?token=wrong-token")
    assert response.status_code == 401


def test_settings_persist_and_reset(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path / "logs", max_workers=2)
    with _test_client(create_app(settings)) as client:
        response = client.put(
            "/api/settings",
            json={
                "max_workers": 3,
                "parallel_workers": 2,
                "default_output_dir": str(tmp_path / "outputs"),
                "video_frames": {
                    "recursive": False,
                    "frame_interval": 25,
                    "resize": True,
                    "width": 800,
                    "height": 600,
                    "resize_mode": "direct",
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["max_workers"] == 3
        assert response.json()["parallel_workers"] == 2
        assert client.app.state.task_manager.max_workers == 3

    with _test_client(create_app(settings)) as client:
        persisted = client.get("/api/settings").json()
        assert persisted["max_workers"] == 3
        assert persisted["parallel_workers"] == 2
        assert persisted["video_frames"]["frame_interval"] == 25
        reset = client.post("/api/settings/reset").json()
        assert reset["max_workers"] == 2
        assert reset["parallel_workers"] == 0
        assert reset["default_output_dir"] is None
        assert reset["video_frames"]["frame_interval"] == 10


def test_active_and_history_are_separated(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path / "logs")
    with _test_client(create_app(settings)) as client:
        database = client.app.state.database
        task_statuses = {
            "active-task": TaskStatus.RUNNING,
            "completed-task": TaskStatus.COMPLETED,
            "failed-task": TaskStatus.FAILED,
        }
        for task_id, status in task_statuses.items():
            database.create_task(
                task_id=task_id,
                tool_id="video-frames",
                tool_version="1.0.0",
                params={},
                output_path=str(tmp_path / f"result_{task_id[:8]}"),
                status=status,
            )
        database.update_task("failed-task", error_summary="测试失败")

        active = client.get("/api/tasks/active").json()
        assert [task["id"] for task in active] == ["active-task"]
        history = client.get("/api/tasks/history?limit=1&status=failed").json()
        assert history["total"] == 1
        assert history["items"][0]["id"] == "failed-task"
        assert history["counts"]["completed"] == 1
        assert history["counts"]["failed"] == 1


def test_delete_history_keeps_or_removes_output_as_requested(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path / "logs")
    with _test_client(create_app(settings)) as client:
        database = client.app.state.database
        keep_id = "abcdefgh-keep"
        keep_output = tmp_path / f"result_{keep_id[:8]}"
        keep_output.mkdir()
        database.create_task(
            task_id=keep_id,
            tool_id="video-frames",
            tool_version="1.0.0",
            params={},
            output_path=str(keep_output),
            status=TaskStatus.COMPLETED,
        )
        assert client.delete(f"/api/tasks/{keep_id}").status_code == 200
        assert keep_output.is_dir()
        assert database.get_task(keep_id) is None

        remove_id = "ijklmnop-remove"
        remove_output = tmp_path / f"result_{remove_id[:8]}"
        remove_output.mkdir()
        (remove_output / "frame.jpg").write_bytes(b"frame")
        database.create_task(
            task_id=remove_id,
            tool_id="video-frames",
            tool_version="1.0.0",
            params={},
            output_path=str(remove_output),
            status=TaskStatus.COMPLETED,
        )
        response = client.delete(f"/api/tasks/{remove_id}?delete_output=true")
        assert response.status_code == 200, response.text
        assert response.json()["output_deleted"] is True
        assert not remove_output.exists()


def test_delete_rejects_active_task_and_unsafe_output(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path / "logs")
    with _test_client(create_app(settings)) as client:
        database = client.app.state.database
        database.create_task(
            task_id="unsafe-task",
            tool_id="video-frames",
            tool_version="1.0.0",
            params={},
            output_path=str(tmp_path),
            status=TaskStatus.RUNNING,
        )
        assert client.delete("/api/tasks/unsafe-task").status_code == 409
        database.update_task("unsafe-task", status="completed")
        assert client.delete("/api/tasks/unsafe-task?delete_output=true").status_code == 409
        assert database.get_task("unsafe-task") is not None
