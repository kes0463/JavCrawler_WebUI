"""프로젝트 전역 경량 유틸리티."""

from __future__ import annotations

import time
from typing import Any


def log_ts(msg: str, *, tag: str = "") -> None:
    prefix = f" [{tag}]" if tag else ""
    print(f"[{time.strftime('%H:%M:%S')}]{prefix} {msg}", flush=True)


def tagify(val: Any) -> str:
    """리스트를 쉼표 구분 문자열로, 또는 문자열 그대로 반환."""
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x)
    return str(val or "").strip()
