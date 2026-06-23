"""Main player active — background prefetch/ffmpeg should yield."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_active = False


def set_playback_active(active: bool) -> None:
    global _active
    with _lock:
        _active = bool(active)


def is_playback_active() -> bool:
    with _lock:
        return _active
