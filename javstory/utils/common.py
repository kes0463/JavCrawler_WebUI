"""프로젝트 전역 경량 유틸리티."""

from __future__ import annotations

import time
from typing import Any, Callable


def log_ts(msg: str, *, tag: str = "") -> None:
    prefix = f" [{tag}]" if tag else ""
    print(f"[{time.strftime('%H:%M:%S')}]{prefix} {msg}", flush=True)


def dedupe_preserve_order(
    items: list[str],
    *,
    key: Callable[[str], str] | None = None,
) -> list[str]:
    """순서 유지 중복 제거. ``key``로 비교 키 지정(기본: casefold)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        s = str(item or "").strip()
        if not s:
            continue
        k = key(s) if key else s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def tagify(val: Any) -> str:
    """리스트를 쉼표 구분 문자열로, 또는 문자열 그대로 반환."""
    if isinstance(val, list):
        return ", ".join(dedupe_preserve_order([str(x) for x in val if x]))
    return str(val or "").strip()
