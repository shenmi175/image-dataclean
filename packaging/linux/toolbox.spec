# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()
MODEL_DIR = ROOT / "models" / "dinov3-vits16-pretrain-lvd1689m"

hiddenimports = sorted(
    set(
        [
            "cairo",
            "backend.tools.annotation_visualizer",
            "backend.tools.coco_to_labelme",
            "backend.tools.frame_deduplicator",
            "backend.tools.image_classifier",
            "backend.tools.labelme_to_yolo",
            "backend.tools.video_frames",
            "backend.tools.web_auto_export",
            "backend.tools.yolo_merge",
            "backend.tools.yolo_split",
            "gi",
            "gi.repository.Gdk",
            "gi.repository.Gio",
            "gi.repository.GLib",
            "gi.repository.Gtk",
            "safetensors",
            "torch",
            "torchvision",
            "transformers",
            "uvicorn.logging",
            "uvicorn.loops.auto",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.websockets.auto",
            "webview",
            "webview.platforms.gtk",
        ]
    )
)

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "README.md"), "."),
]
if not MODEL_DIR.is_dir():
    raise SystemExit("缺少 DINOv3 模型，请先在应用中运行一次视频帧清理任务")
datas.append((str(MODEL_DIR), f"models/{MODEL_DIR.name}"))

a = Analysis(
    [str(ROOT / "desktop" / "packaged_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
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
        "IPython",
        "pkg_resources",
        "matplotlib",
        "onnxruntime",
        "pandas",
        "pytest",
        "PyObjCTools",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "qtpy",
        "setuptools",
        "skimage",
        "sklearn",
        "tensorboard",
        "tensorflow",
        "timm",
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
