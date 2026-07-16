from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

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


def test_discovery_is_recursive_and_deduplicates_explicit_files(tmp_path: Path) -> None:
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


def test_video_tool_writes_interval_frames_with_unicode_paths(tmp_path: Path) -> None:
    source = tmp_path / "输入 视频"
    source.mkdir()
    video = source / "演示.avi"
    make_video(video, frames=12)
    output = tmp_path / "输出 图片"
    context = RecordingContext(output)
    params = VideoFramesParams(
        input_files=[video],
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
