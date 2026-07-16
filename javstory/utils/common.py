"""프로젝트 전역 경량 유틸리티."""

from __future__ import annotations

import sys
import time
from typing import Any, Callable


def safe_console_print(text: str) -> None:
    """print()가 콘솔 코드페이지(예: Windows cp949)에서 인코딩 못 하는 문자(이모지,
    em-dash 등)를 만나도 죽지 않게 함 — 로그 한 줄 때문에 작업 전체가 실패하면 안 됨."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


def log_ts(msg: str, *, tag: str = "") -> None:
    prefix = f" [{tag}]" if tag else ""
    safe_console_print(f"[{time.strftime('%H:%M:%S')}]{prefix} {msg}")


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
