from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

_dialog_lock = threading.Lock()


def select_directory(title: str = "选择目录") -> str | None:
    from tkinter import Tk, filedialog

    with _dialog_lock:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(title=title, mustexist=True, parent=root)
            return selected or None
        finally:
            root.destroy()


def select_files(title: str = "选择视频") -> list[str]:
    from tkinter import Tk, filedialog

    with _dialog_lock:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askopenfilenames(
                title=title,
                filetypes=[
                    ("视频文件", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv"),
                    ("所有文件", "*.*"),
                ],
                parent=root,
            )
            return list(selected)
        finally:
            root.destroy()


def open_path(path: str) -> None:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(str(target))
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        uri = target.as_uri()
        method = "ShowFolders" if target.is_dir() else "ShowItems"
        gdbus = shutil.which("gdbus")
        if gdbus:
            try:
                subprocess.run(
                    [
                        gdbus,
                        "call",
                        "--session",
                        "--dest",
                        "org.freedesktop.FileManager1",
                        "--object-path",
                        "/org/freedesktop/FileManager1",
                        "--method",
                        f"org.freedesktop.FileManager1.{method}",
                        f"['{uri}']",
                        "",
                    ],
                    check=True,
                    timeout=3,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (OSError, subprocess.SubprocessError):
                pass

        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        preferred: list[str] = []
        if "cinnamon" in desktop:
            preferred.append("nemo")
        elif "kde" in desktop:
            preferred.append("dolphin")
        elif "xfce" in desktop:
            preferred.append("thunar")
        elif "gnome" in desktop or "ubuntu" in desktop:
            preferred.append("nautilus")
        candidates = preferred + ["nautilus", "nemo", "dolphin", "thunar", "pcmanfm"]
        folder = target if target.is_dir() else target.parent
        for candidate in dict.fromkeys(candidates):
            executable = shutil.which(candidate)
            if executable:
                subprocess.Popen([executable, str(folder)], start_new_session=True)
                return
        raise RuntimeError("未找到可用的文件管理器")
