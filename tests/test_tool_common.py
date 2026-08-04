import threading
import time
from pathlib import Path

import pytest

from backend.tools.common import (
    discover_files,
    parallel_map,
    transfer_file,
    validate_output_outside,
)
from tests.tool_test_utils import RecordingContext


def test_discovery_filters_suffixes_and_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "input"
    nested = root / "nested"
    nested.mkdir(parents=True)
    image = nested / "A.JPG"
    image.write_bytes(b"image")
    (root / "note.txt").write_text("ignore", encoding="utf-8")
    link = root / "linked.jpg"
    try:
        link.symlink_to(image)
    except OSError:
        pass

    assert discover_files(root, {".jpg"}) == [image]
    assert discover_files(root, {".jpg"}, recursive=False) == []


def test_atomic_transfer_supports_copy_move_and_rename(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"new")
    output = tmp_path / "output"
    context = RecordingContext(output)
    target = output / "target.jpg"
    target.parent.mkdir()
    target.write_bytes(b"existing")

    renamed = transfer_file(source, target, context)
    assert renamed == output / "target_1.jpg"
    assert renamed.read_bytes() == b"new"
    assert source.is_file()

    moved = transfer_file(source, output / "moved.jpg", context, mode="move")
    assert moved is not None and moved.read_bytes() == b"new"
    assert not source.exists()


def test_output_cannot_be_nested_in_input(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="输出目录不能"):
        validate_output_outside(source / "output", [source])


def test_parallel_map_uses_multiple_threads_and_keeps_input_indexes(tmp_path: Path) -> None:
    context = RecordingContext(tmp_path, parallel_workers=3)
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def work(value: int) -> int:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return value * 2

    completed = list(parallel_map(range(8), work, context))
    ordered = [result.value for result in sorted(completed, key=lambda item: item.index)]

    assert maximum_active >= 2
    assert ordered == [value * 2 for value in range(8)]
    assert any("3 个线程" in message for message in context.logs)
