"""Grok/사용자 time_range 문자열 → (start_sec, end_sec)."""

from __future__ import annotations

import re
from typing import Tuple

# HH:MM:SS[.frac] ~ HH:MM:SS[.frac] (선행 공백·꼬리 주석 허용)
_RANGE_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?\s*[~～〜-]\s*(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?",
    re.UNICODE,
)


def _part_to_sec(h: str, m: str, s: str, frac: str | None) -> float:
    base = int(h) * 3600 + int(m) * 60 + int(s)
    if frac:
        # 소수 초: "05" -> 0.05 가 아니라 프레임일 수 있음 — 길이에 따라 처리
        if len(frac) <= 2:
            base += int(frac) / (10 ** len(frac))
        else:
            base += float("0." + frac)
    return float(base)


def parse_time_range(text: str | None) -> Tuple[float | None, float | None]:
    """
    '00:03:43.05 ~ 00:31:53.6 (자막 기준)' 형태에서 구간 초 단위 추출.
    파싱 실패 시 (None, None).
    """
    if not text or not isinstance(text, str):
        return None, None
    m = _RANGE_RE.search(text.strip())
    if not m:
        return None, None
    h1, m1, s1, f1, h2, m2, s2, f2 = m.groups()
    try:
        a = _part_to_sec(h1, m1, s1, f1)
        b = _part_to_sec(h2, m2, s2, f2)
    except (ValueError, TypeError):
        return None, None
    if a > b:
        a, b = b, a
    return a, b


def apply_parsed_range_to_scene_dict(scene: dict) -> dict:
    """SceneEntry 직렬화 dict에 start_sec/end_sec 채움 (없을 때만)."""
    tr = scene.get("time_range")
    a, b = parse_time_range(str(tr) if tr is not None else "")
    if a is not None and scene.get("start_sec") is None:
        scene["start_sec"] = a
    if b is not None and scene.get("end_sec") is None:
        scene["end_sec"] = b
    return scene
