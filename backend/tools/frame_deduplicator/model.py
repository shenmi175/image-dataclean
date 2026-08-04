from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

MODEL_ID = "facebook/dinov3-vits16-pretrain-lvd1689m"
MODEL_REVISION = "2e601320d0545509ab03374e2f8707f303e1de7a"
MODEL_NAME = "dinov3-vits16-pretrain-lvd1689m"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = PROJECT_ROOT / "models" / MODEL_NAME
MODELSCOPE_BASE = f"https://modelscope.cn/models/{MODEL_ID}/resolve/master"


@dataclass(frozen=True)
class ModelFile:
    name: str
    sha256: str
    size: int

    @property
    def url(self) -> str:
        return f"{MODELSCOPE_BASE}/{self.name}"


MODEL_FILES = (
    ModelFile(
        "config.json",
        "9481247be9f95a134a5599402b4bfc838eecdf9a7fffbf4debd1c70ec213898b",
        743,
    ),
    ModelFile(
        "preprocessor_config.json",
        "960c41d1f3a7778b936365769a2d90550b318a6c0a53a0296957adacfe5e0dd7",
        585,
    ),
    ModelFile(
        "model.safetensors",
        "4610ad75edef83e75afdebf162d148dc628045ea6cbb83d67d4708c709c4f91d",
        86_406_384,
    ),
    ModelFile(
        "LICENSE.md",
        "25d122eb8f5b880fd23c736fb6ea8018ee45c12237e00b8a86d14c653904999e",
        7_503,
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_model_file(path: Path, expected: ModelFile) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected.size
        and sha256_file(path) == expected.sha256
    )


def download_model_file(
    expected: ModelFile,
    target: Path,
    checkpoint: Callable[[], None] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.part")
    digest = hashlib.sha256()
    written = 0
    request = Request(expected.url, headers={"User-Agent": "automation-toolbox/0.3.1"})
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
            while True:
                if checkpoint:
                    checkpoint()
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        if written != expected.size or digest.hexdigest() != expected.sha256:
            raise RuntimeError(f"模型文件校验失败: {expected.name}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _all_files_valid(model_dir: Path, files: Sequence[ModelFile]) -> bool:
    return all(valid_model_file(model_dir / item.name, item) for item in files)


def ensure_model_files(
    model_dir: Path = MODEL_DIR,
    files: Sequence[ModelFile] = MODEL_FILES,
    *,
    checkpoint: Callable[[], None] | None = None,
    downloader: Callable[[ModelFile, Path, Callable[[], None] | None], None]
    | None = None,
) -> Path:
    """Download a verified local snapshot without using third-party caches."""
    if _all_files_valid(model_dir, files):
        return model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    lock_path = model_dir / ".download.lock"
    owns_lock = False
    started = time.monotonic()
    while not owns_lock:
        if checkpoint:
            checkpoint()
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if _all_files_valid(model_dir, files):
                return model_dir
            if time.monotonic() - started > 600:
                raise TimeoutError("等待其他任务下载 DINOv3 模型超时") from None
            try:
                if time.time() - lock_path.stat().st_mtime > 1800:
                    lock_path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
            time.sleep(0.2)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        owns_lock = True
    try:
        fetch = downloader or download_model_file
        for expected in files:
            target = model_dir / expected.name
            if not valid_model_file(target, expected):
                target.unlink(missing_ok=True)
                fetch(expected, target, checkpoint)
        if not _all_files_valid(model_dir, files):
            raise RuntimeError("DINOv3 模型快照不完整")
        return model_dir
    finally:
        if owns_lock:
            lock_path.unlink(missing_ok=True)
