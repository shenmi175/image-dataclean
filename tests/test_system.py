from pathlib import Path
from unittest.mock import Mock

from backend.infrastructure import system


def test_open_path_uses_file_manager_dbus(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run = Mock()
    popen = Mock()
    monkeypatch.setattr(
        system.shutil,
        "which",
        lambda name: "/usr/bin/gdbus" if name == "gdbus" else None,
    )
    monkeypatch.setattr(system.subprocess, "run", run)
    monkeypatch.setattr(system.subprocess, "Popen", popen)

    system.open_path(str(tmp_path))

    command = run.call_args.args[0]
    assert "org.freedesktop.FileManager1.ShowFolders" in command
    assert tmp_path.as_uri() in command[-2]
    popen.assert_not_called()


def test_open_path_falls_back_to_real_file_manager(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def executable(name: str) -> str | None:
        if name == "gdbus":
            return "/usr/bin/gdbus"
        if name == "nautilus":
            return "/usr/bin/nautilus"
        return None

    popen = Mock()
    monkeypatch.setattr(system.shutil, "which", executable)
    monkeypatch.setattr(
        system.subprocess,
        "run",
        Mock(side_effect=system.subprocess.TimeoutExpired("gdbus", 3)),
    )
    monkeypatch.setattr(system.subprocess, "Popen", popen)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")

    system.open_path(str(tmp_path))

    assert popen.call_args.args[0] == ["/usr/bin/nautilus", str(tmp_path)]
