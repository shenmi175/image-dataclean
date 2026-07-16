# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()

hiddenimports = sorted(
    set(
        [
            "cairo",
            "gi",
            "gi.repository.Gdk",
            "gi.repository.Gio",
            "gi.repository.GLib",
            "gi.repository.Gtk",
            "uvicorn.logging",
            "uvicorn.loops.auto",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.websockets.auto",
            "webview.platforms.gtk",
        ]
    )
)

a = Analysis(
    [str(ROOT / "desktop" / "packaged_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ROOT / "README.md"), "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        "gi": {
            "icons": ["Adwaita"],
            "themes": ["Adwaita"],
            "languages": ["en"],
        }
    },
    runtime_hooks=[],
    excludes=[
        "android",
        "cefpython3",
        "clr",
        "Foundation",
        "pkg_resources",
        "PyObjCTools",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "qtpy",
        "setuptools",
        "_tkinter",
        "tkinter",
        "WebKit",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="automation-toolbox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AutomationToolbox",
)
