from __future__ import annotations

import json
import multiprocessing
import os
import secrets
import socket
import sys
import threading
import time
from contextlib import closing
from urllib.error import URLError
from urllib.request import Request, urlopen

# DMA-BUF can paint a white window under VMware/NoMachine. Disabling only that
# renderer preserves WebKit compositing and keeps navigation responsive.
if sys.platform.startswith("linux"):
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    if os.environ.get("TOOLBOX_SOFTWARE_RENDERING") == "1":
        os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

import uvicorn
import webview

from backend.app import create_app
from backend.core.settings import Settings


class NativeDialogs:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def select_directory(self) -> str | None:
        if self.window is None:
            return None
        selected = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return selected[0] if selected else None

    def select_files(self, options: dict | None = None) -> list[str]:
        if self.window is None:
            return []
        options = options or {}
        extensions = options.get("extensions") or []
        patterns = ";".join(
            f"*{item if str(item).startswith('.') else '.' + str(item)}" for item in extensions
        )
        file_types = (f"支持的文件 ({patterns})",) if patterns else ("所有文件 (*.*)",)
        selected = self.window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=bool(options.get("multiple", True)),
            file_types=file_types,
        )
        return list(selected or [])


def find_available_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_backend(port: int, token: str) -> None:
    settings = Settings(port=port, auth_disabled=False, session_token=token)
    debug = os.environ.get("TOOLBOX_DEBUG") == "1"
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=port,
        log_level="debug" if debug else "warning",
        access_log=debug,
    )


def wait_for_backend(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    health_url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError("FastAPI backend did not become ready in time")


def active_tasks(port: int, token: str) -> list[dict]:
    request = Request(
        f"http://127.0.0.1:{port}/api/tasks?limit=500",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(request, timeout=2) as response:
        tasks = json.loads(response.read())
    active = {"pending", "running", "paused", "cancelling"}
    return [task for task in tasks if task["status"] in active]


def cancel_tasks(port: int, token: str, tasks: list[dict]) -> None:
    for task in tasks:
        request = Request(
            f"http://127.0.0.1:{port}/api/tasks/{task['id']}/cancel",
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=2):
                pass
        except URLError:
            continue


def wait_then_close(window: webview.Window, port: int, token: str) -> None:
    while True:
        try:
            if not active_tasks(port, token):
                window.destroy()
                return
        except URLError:
            window.destroy()
            return
        time.sleep(0.5)


def main() -> None:
    port = find_available_port()
    token = secrets.token_urlsafe(32)
    # The backend must not be daemonic because it owns isolated task Worker processes.
    backend = multiprocessing.Process(target=run_backend, args=(port, token), daemon=False)
    backend.start()

    try:
        wait_for_backend(port)
        native_dialogs = NativeDialogs()
        window = webview.create_window(
            "自动化工具箱",
            f"http://127.0.0.1:{port}/#token={token}",
            width=1180,
            height=760,
            min_size=(720, 520),
            resizable=True,
            js_api=native_dialogs,
        )
        native_dialogs.window = window

        def on_closing() -> bool:
            try:
                tasks = active_tasks(port, token)
            except URLError:
                return True
            if not tasks:
                return True
            keep_running = window.evaluate_js(
                "window.confirm('仍有任务在运行。\\n确定：最小化到后台继续\\n取消：选择其他退出方式')"
            )
            if keep_running:
                window.minimize()
                return False
            wait_for_completion = window.evaluate_js(
                "window.confirm('确定：等待任务完成后自动退出\\n取消：取消全部任务并退出')"
            )
            if wait_for_completion:
                window.minimize()
                threading.Thread(
                    target=wait_then_close,
                    args=(window, port, token),
                    daemon=True,
                ).start()
                return False
            cancel_tasks(port, token, tasks)
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                try:
                    if not active_tasks(port, token):
                        break
                except URLError:
                    break
                time.sleep(0.1)
            return True

        window.events.closing += on_closing
        webview.start(debug=os.environ.get("TOOLBOX_DEBUG") == "1")
    finally:
        if backend.is_alive():
            backend.terminate()
            backend.join(timeout=5)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
