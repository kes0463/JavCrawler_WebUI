"""동영상 확장자 — GUI 큐와 multipart 공통."""

from __future__ import annotations

from pathlib import Path

from javstory.config.app_config import VIDEO_EXTENSIONS

_EXTRA = (".m4v",)
VIDEO_EXT_SET = frozenset(e.lower() for e in VIDEO_EXTENSIONS) | frozenset(e.lower() for e in _EXTRA)


def is_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXT_SET
