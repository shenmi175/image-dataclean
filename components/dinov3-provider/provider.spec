# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path.cwd()
SOURCE = ROOT / "components" / "dinov3-provider" / "src"

hiddenimports = sorted(
    set(
        collect_submodules("transformers.models.dinov3")
        + ["numpy", "PIL", "safetensors", "safetensors.torch", "torch", "transformers"]
    )
)

a = Analysis(
    [str(SOURCE / "automation_toolbox_dinov3_provider" / "__main__.py")],
    pathex=[str(SOURCE)],
    datas=collect_data_files("transformers"),
    hiddenimports=hiddenimports,
    excludes=["pygments", "pytest", "setuptools", "tkinter", "_tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="automation-toolbox-provider-dinov3",
    console=True,
    strip=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AutomationToolboxProviderDINOv3",
)
