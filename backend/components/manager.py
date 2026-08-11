from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from backend.components.catalog import BUILTIN_COMPONENTS, ComponentDescriptor
from backend.core.settings import default_state_dir
from backend.version import __version__

GITHUB_REPOSITORY = "shenmi175/image-dataclean"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            target = (destination / member.name).resolve()
            if (
                target != destination_resolved
                and destination_resolved not in target.parents
            ):
                raise RuntimeError(f"组件压缩包包含不安全路径: {member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"组件压缩包不允许符号链接: {member.name}")
        package.extractall(destination, filter="data")


class ComponentManager:
    def __init__(
        self,
        component_dir: Path | None = None,
        model_dir: Path | None = None,
        *,
        repository: str = GITHUB_REPOSITORY,
    ) -> None:
        state_dir = default_state_dir()
        self.component_dir = component_dir or Path(
            os.environ.get("TOOLBOX_COMPONENT_DIR", state_dir / "components")
        )
        self.model_dir = model_dir or Path(
            os.environ.get("TOOLBOX_MODEL_DIR", state_dir / "models")
        )
        self.repository = repository

    def descriptor(self, component_id: str) -> ComponentDescriptor:
        try:
            return BUILTIN_COMPONENTS[component_id]
        except KeyError as exc:
            raise KeyError(f"未知模型组件: {component_id}") from exc

    def executable_path(self, descriptor: ComponentDescriptor) -> Path:
        return self.component_dir / descriptor.id / descriptor.version / descriptor.executable

    def installed(self, descriptor: ComponentDescriptor) -> bool:
        return self.executable_path(descriptor).is_file()

    def command(self, component_id: str) -> list[str]:
        descriptor = self.descriptor(component_id)
        override = os.environ.get("TOOLBOX_DINOV3_PROVIDER_COMMAND")
        if override and component_id == "dinov3-cpu":
            return shlex.split(override)
        executable = self.executable_path(descriptor)
        if not executable.is_file():
            raise RuntimeError(f"模型组件尚未安装: {descriptor.name}")
        return [str(executable)]

    def public_state(
        self,
        descriptor: ComponentDescriptor,
        acceptance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        accepted = bool(
            acceptance
            and acceptance.get("license_sha256") == descriptor.license.sha256
            and acceptance.get("accepted") is True
        )
        result = descriptor.as_dict()
        result.update(
            {
                "installed": self.installed(descriptor),
                "license_accepted": accepted,
            }
        )
        return result

    def _release_asset(self, descriptor: ComponentDescriptor) -> tuple[str, str, int]:
        api_url = (
            f"https://api.github.com/repos/{self.repository}/releases/tags/"
            f"{descriptor.release_tag}"
        )
        request = Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"automation-toolbox/{__version__}",
            },
        )
        with urlopen(request, timeout=30) as response:
            release = json.load(response)
        for asset in release.get("assets", []):
            if asset.get("name") != descriptor.asset_name:
                continue
            digest = str(asset.get("digest") or "")
            if not digest.startswith("sha256:"):
                raise RuntimeError("GitHub Release 资产缺少 SHA-256 摘要")
            return (
                str(asset["browser_download_url"]),
                digest.removeprefix("sha256:"),
                int(asset.get("size") or 0),
            )
        raise RuntimeError(f"Release 中缺少模型组件资产: {descriptor.asset_name}")

    def ensure_installed(
        self,
        component_id: str,
        *,
        checkpoint: Callable[[], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        descriptor = self.descriptor(component_id)
        target_executable = self.executable_path(descriptor)
        if target_executable.is_file():
            return target_executable
        if os.environ.get("TOOLBOX_DINOV3_PROVIDER_COMMAND"):
            return Path(self.command(component_id)[0])

        url, expected_sha256, expected_size = self._release_asset(descriptor)
        self.component_dir.mkdir(parents=True, exist_ok=True)
        staging_parent = self.component_dir / ".staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{component_id}-", dir=staging_parent))
        archive = staging / descriptor.asset_name
        unpacked = staging / "unpacked"
        try:
            request = Request(
                url,
                headers={"User-Agent": f"automation-toolbox/{__version__}"},
            )
            written = 0
            digest = hashlib.sha256()
            with urlopen(request, timeout=60) as response, archive.open("wb") as handle:
                while True:
                    if checkpoint:
                        checkpoint()
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    if progress:
                        progress(written, expected_size)
            if expected_size and written != expected_size:
                raise RuntimeError("模型组件下载大小不匹配")
            if digest.hexdigest() != expected_sha256:
                raise RuntimeError("模型组件 SHA-256 校验失败")
            unpacked.mkdir()
            _safe_extract(archive, unpacked)
            candidate = unpacked / descriptor.executable
            if not candidate.is_file():
                raise RuntimeError("模型组件压缩包缺少可执行程序")
            candidate.chmod(0o755)
            final_dir = target_executable.parent
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.rename(unpacked, final_dir)
            except OSError:
                # Another task may have won the atomic install race. Component
                # versions are immutable, so an existing valid target is enough.
                if not target_executable.is_file():
                    raise
            return target_executable
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def provider_environment(manager: ComponentManager) -> dict[str, str]:
    environment = os.environ.copy()
    environment["TOOLBOX_MODEL_DIR"] = str(manager.model_dir)
    environment["PYTHONUNBUFFERED"] = "1"
    if getattr(sys, "frozen", False):
        environment.pop("PYTHONPATH", None)
    return environment
