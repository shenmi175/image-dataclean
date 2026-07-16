from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
from backend.core.settings import Settings, get_settings
from backend.infrastructure.database import Database
from backend.scheduler.events import EventBroker
from backend.scheduler.manager import TaskManager

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.resolved_database_path)
        broker = EventBroker()
        task_manager = TaskManager(
            database,
            broker,
            max_workers=resolved_settings.max_workers,
            cancel_timeout=resolved_settings.cancel_timeout,
        )
        application.state.settings = resolved_settings
        application.state.default_max_workers = resolved_settings.max_workers
        application.state.database = database
        application.state.event_broker = broker
        application.state.task_manager = task_manager
        await task_manager.start()
        try:
            yield
        finally:
            await task_manager.stop()

    application = FastAPI(
        title="Automation Toolbox API",
        version="0.2.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def authenticate(request: Request, call_next):  # type: ignore[no-untyped-def]
        if (
            resolved_settings.auth_disabled
            or request.url.path == "/api/health"
            or request.url.path == "/api/events/stream"
            or not request.url.path.startswith("/api/")
        ):
            return await call_next(request)
        authorization = request.headers.get("authorization")
        if authorization != f"Bearer {resolved_settings.session_token}":
            return JSONResponse({"detail": "未授权"}, status_code=401)
        return await call_next(request)

    application.include_router(api_router, prefix="/api")

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @application.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> FileResponse:
            requested = FRONTEND_DIST / path
            if path and requested.is_file():
                return FileResponse(requested)
            return FileResponse(FRONTEND_DIST / "index.html")

    return application


app = create_app()
