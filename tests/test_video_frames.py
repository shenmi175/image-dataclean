from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.tools.base import TaskCancelled, TaskContext
from backend.tools.video_frames import VideoFramesParams, VideoFramesTool
from backend.tools.video_frames.executor import (
    direct_resize,
    discover_videos,
    letterbox_resize,
)


class RecordingContext(TaskContext):
    def __init__(self, output_path: Path) -> None:
        self.task_id = "test-task"
        self.output_path = str(output_path)
        self.parallel_workers = 3
        self.progress: list[tuple[int, int | None]] = []
        self.logs: list[str] = []
        self.failures: list[tuple[str, str]] = []
        self.cancelled = False

    def wait_if_paused(self) -> None:
        return

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled

    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
        *,
        success_count: int | None = None,
        failure_count: int | None = None,
        force: bool = False,
    ) -> None:
        self.progress.append((current, total))

    def log(self, level: str, message: str) -> None:
        self.logs.append(message)

    def record_failure(self, item: str, error: str) -> None:
        self.failures.append((item, error))


def make_video(path: Path, frames: int = 12, size: tuple[int, int] = (48, 32)) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        size,
    )
    assert writer.isOpened()
    for index in range(frames):
        frame = np.full((size[1], size[0], 3), index * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_resize_modes_have_expected_shape() -> None:
    image = np.zeros((20, 40, 3), dtype=np.uint8)

    assert letterbox_resize(image, (64, 64)).shape == (64, 64, 3)
    assert direct_resize(image, (32, 24)).shape == (24, 32, 3)


def test_legacy_discovery_is_recursive_and_deduplicates_explicit_files(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "视频" / "子目录"
    nested.mkdir(parents=True)
    video = nested / "样例.avi"
    make_video(video, frames=2)
    params = VideoFramesParams(
        input_dir=tmp_path / "视频",
        input_files=[video],
        output_dir=tmp_path / "输出",
    )

    discovered = discover_videos(params)

    assert [item[0] for item in discovered] == [video.resolve()]


def test_input_path_accepts_a_single_video(tmp_path: Path) -> None:
    video = tmp_path / "single.avi"
    make_video(video, frames=2)

    params = VideoFramesParams(input_path=video, output_dir=tmp_path / "output")

    assert discover_videos(params) == [(video.resolve(), None)]


def test_input_path_directory_honors_recursive_setting(tmp_path: Path) -> None:
    source = tmp_path / "videos"
    nested = source / "nested"
    nested.mkdir(parents=True)
    direct_video = source / "direct.avi"
    nested_video = nested / "nested.avi"
    make_video(direct_video, frames=2)
    make_video(nested_video, frames=2)

    shallow = VideoFramesParams(
        input_path=source,
        recursive=False,
        output_dir=tmp_path / "shallow",
    )
    recursive = VideoFramesParams(
        input_path=source,
        recursive=True,
        output_dir=tmp_path / "recursive",
    )

    assert [item[0] for item in discover_videos(shallow)] == [direct_video.resolve()]
    assert [item[0] for item in discover_videos(recursive)] == [
        direct_video.resolve(),
        nested_video.resolve(),
    ]


def test_input_path_takes_precedence_over_legacy_sources(tmp_path: Path) -> None:
    selected = tmp_path / "selected.avi"
    legacy = tmp_path / "legacy.avi"
    make_video(selected, frames=2)
    make_video(legacy, frames=2)
    params = VideoFramesParams(
        input_path=selected,
        input_files=[legacy],
        input_dir=tmp_path,
        output_dir=tmp_path / "output",
    )

    assert discover_videos(params) == [(selected.resolve(), None)]


def test_input_path_rejects_invalid_and_non_video_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="请选择一个视频文件或视频目录"):
        VideoFramesParams(input_path="", output_dir=tmp_path / "output")

    with pytest.raises(ValueError, match="输入路径不存在"):
        VideoFramesParams(
            input_path=tmp_path / "missing.avi",
            output_dir=tmp_path / "output",
        )

    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a video", encoding="utf-8")
    with pytest.raises(ValueError, match="不是支持的视频格式"):
        VideoFramesParams(input_path=text_file, output_dir=tmp_path / "output")


def test_video_tool_writes_interval_frames_with_unicode_paths(tmp_path: Path) -> None:
    source = tmp_path / "输入 视频"
    source.mkdir()
    video = source / "演示.avi"
    make_video(video, frames=12)
    output = tmp_path / "输出 图片"
    context = RecordingContext(output)
    params = VideoFramesParams(
        input_path=video,
        output_dir=output.parent,
        frame_interval=3,
        resize=True,
        width=64,
        height=64,
        resize_mode="letterbox",
    )

    result = VideoFramesTool().run(params, context)

    images = sorted(output.rglob("*.jpg"))
    assert len(images) == 4
    assert result["success_count"] == 4
    decoded = cv2.imdecode(np.fromfile(images[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (64, 64, 3)
    assert not context.failures
