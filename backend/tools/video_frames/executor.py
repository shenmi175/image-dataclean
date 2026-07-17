from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.tools.base import TaskContext, Tool
from backend.tools.common import VIDEO_SUFFIXES, checkpoint, discover_files
from backend.tools.video_frames.spec import VideoFramesParams

VIDEO_EXTENSIONS = VIDEO_SUFFIXES


def letterbox_resize(
    frame: np.ndarray,
    target_size: tuple[int, int],
    color: tuple[int, int, int] = (114, 114, 114),
) -> np.ndarray:
    height, width = frame.shape[:2]
    target_width, target_height = target_size
    if height == 0 or width == 0:
        return frame
    scale = min(target_width / width, target_height / height)
    new_width = max(int(round(width * scale)), 1)
    new_height = max(int(round(height * scale)), 1)
    if (new_width, new_height) != (width, height):
        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    horizontal = target_width - new_width
    vertical = target_height - new_height
    return cv2.copyMakeBorder(
        frame,
        vertical // 2,
        vertical - vertical // 2,
        horizontal // 2,
        horizontal - horizontal // 2,
        cv2.BORDER_CONSTANT,
        value=color,
    )


def direct_resize(frame: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    return cv2.resize(frame, target_size, interpolation=cv2.INTER_LINEAR)


def write_jpeg(path: Path, image: np.ndarray, quality: int = 95) -> bool:
    encoded, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.tobytes())
    return True


def discover_videos(params: VideoFramesParams) -> list[tuple[Path, Path | None]]:
    candidates: list[tuple[Path, Path | None]] = []
    if params.input_dir is not None:
        root = params.input_dir.expanduser().resolve()
        candidates.extend(
            (path, root)
            for path in discover_files(root, VIDEO_EXTENSIONS, recursive=params.recursive)
        )
    candidates.extend((path.expanduser().resolve(), None) for path in params.input_files)

    discovered: dict[str, tuple[Path, Path | None]] = {}
    for path, root in candidates:
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            discovered.setdefault(str(path), (path, root))
    return sorted(discovered.values(), key=lambda item: str(item[0]).casefold())


def output_folder_for(
    video_path: Path,
    source_root: Path | None,
    used: set[str],
) -> Path:
    if source_root is not None:
        relative = video_path.relative_to(source_root).with_suffix("")
    else:
        relative = Path(video_path.stem)
    key = relative.as_posix().casefold()
    if key in used:
        digest = hashlib.sha256(str(video_path).encode()).hexdigest()[:8]
        relative = relative.with_name(f"{relative.name}_{digest}")
        key = relative.as_posix().casefold()
    used.add(key)
    return relative


class VideoFramesTool(Tool):
    id = "video-frames"
    name = "视频转图片"
    category = "媒体处理"
    version = "1.0.0"
    description = "按固定帧间隔批量提取视频画面，可选等比填充或直接缩放。"
    params_model = VideoFramesParams
    ui_schema = {
        "order": [
            "input_files",
            "input_dir",
            "recursive",
            "output_dir",
            "frame_interval",
            "resize",
            "width",
            "height",
            "resize_mode",
        ],
        "widgets": {
            "input_files": "file-list",
            "input_dir": "directory",
            "output_dir": "directory",
            "resize_mode": "radio",
        },
        "file_filters": {"input_files": sorted(VIDEO_EXTENSIONS)},
        "picker_titles": {"input_files": "选择视频文件"},
        "submit_label": "创建视频转图片任务",
        "notice": "文件和目录可同时使用，重复视频会自动去重。每次任务都会创建独立输出目录。",
    }

    def run(self, params: VideoFramesParams, context: TaskContext) -> dict[str, Any]:
        videos = discover_videos(params)
        if not videos:
            raise ValueError("没有找到支持的视频文件")

        output_root = Path(context.output_path)
        output_root.mkdir(parents=True, exist_ok=True)
        context.log("info", f"发现 {len(videos)} 个视频")

        total_frames = 0
        all_totals_known = True
        for video, _ in videos:
            capture = cv2.VideoCapture(str(video))
            count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if capture.isOpened() else 0
            capture.release()
            if count <= 0:
                all_totals_known = False
            else:
                total_frames += count

        current = 0
        written = 0
        failures = 0
        successful_videos = 0
        used_folders: set[str] = set()
        started = time.monotonic()

        for video, source_root in videos:
            checkpoint(context)
            context.log("info", f"开始处理 {video.name}")
            capture = cv2.VideoCapture(str(video))
            if not capture.isOpened():
                failures += 1
                context.record_failure(str(video), "无法打开视频")
                continue

            relative_folder = output_folder_for(video, source_root, used_folders)
            destination = output_root / relative_folder
            frame_index = 0
            video_written = 0
            try:
                while True:
                    checkpoint(context)
                    ok, frame = capture.read()
                    if not ok:
                        break
                    current += 1
                    if frame_index % params.frame_interval == 0:
                        if params.resize:
                            size = (params.width, params.height)
                            frame = (
                                letterbox_resize(frame, size)
                                if params.resize_mode == "letterbox"
                                else direct_resize(frame, size)
                            )
                        target = destination / f"{video.stem}_{frame_index:06d}.jpg"
                        if write_jpeg(target, frame):
                            written += 1
                            video_written += 1
                        else:
                            failures += 1
                            context.record_failure(str(target), "JPEG 写入失败")
                    frame_index += 1
                    elapsed = max(time.monotonic() - started, 0.001)
                    context.report_progress(
                        current,
                        total_frames if all_totals_known else None,
                        f"正在处理 {video.name} · {current / elapsed:.1f} 帧/秒",
                        success_count=written,
                        failure_count=failures,
                    )
            finally:
                capture.release()

            if video_written > 0:
                successful_videos += 1
            else:
                failures += 1
                context.record_failure(str(video), "视频未产生任何输出图片")

        if successful_videos == 0:
            raise RuntimeError("所有视频均处理失败")
        context.report_progress(
            current,
            total_frames if all_totals_known else current,
            f"处理完成，共输出 {written} 张图片",
            success_count=written,
            failure_count=failures,
            force=True,
        )
        return {
            "output_path": str(output_root),
            "success_count": written,
            "failure_count": failures,
            "message": f"已输出 {written} 张图片",
        }
