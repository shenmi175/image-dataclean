from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
VIDEO_SUFFIXES = frozenset({".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv"})


def discover_files(
    root: Path,
    suffixes: Collection[str],
    *,
    recursive: bool = True,
    follow_symlinks: bool = False,
) -> list[Path]:
    normalized = {suffix.lower() for suffix in suffixes}
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        (
            path
            for path in iterator
            if path.is_file()
            and (follow_symlinks or not path.is_symlink())
            and path.suffix.lower() in normalized
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def image_files(root: Path, *, recursive: bool = True) -> list[Path]:
    return discover_files(root, IMAGE_SUFFIXES, recursive=recursive)


def find_image(directory: Path, stem: str) -> Path | None:
    matches = [
        path for path in directory.glob(f"{stem}.*") if path.suffix.lower() in IMAGE_SUFFIXES
    ]
    if len(matches) > 1:
        raise ValueError(f"同名图像不唯一: {directory / stem}")
    return matches[0] if matches else None
