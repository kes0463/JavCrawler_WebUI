"""폴더·파일명 기반 자체자막·모파 램프 감지 (GUI 비의존)."""

from __future__ import annotations

import re
from pathlib import Path

SELF_SUBTITLE_MARKER = "자체자막"

_SELF_SUBTITLE_NAME_RE = re.compile(r"자체\s*자막")
_MOPA_NAME_RE = re.compile(
    r"(모자이크\s*(삭제|제거|파괴)|uncen|uncensored|reducing\s*mosaic)",
    re.IGNORECASE,
)


def _collect_path_texts(video_path: Path | None, folder_path: str | None) -> list[str]:
    target_texts: list[str] = []
    if video_path:
        target_texts.append(video_path.name)
        target_texts.extend(video_path.parts)
    fp = (folder_path or "").strip()
    if fp:
        try:
            p_fp = Path(fp)
            target_texts.append(p_fp.name)
            target_texts.extend(p_fp.parts)
        except Exception:
            pass
    return target_texts


def path_contains_self_subtitle_marker(
    video_path: Path | None,
    folder_path: str | None,
    product_code: str = "",
) -> bool:
    """폴더·파일 이름에「자체자막」「자체 자막」연속 문자열만 허용."""
    _ = product_code
    for text in _collect_path_texts(video_path, folder_path):
        if _SELF_SUBTITLE_NAME_RE.search(text):
            return True
    return False


def path_contains_mopa_marker(
    video_path: Path | None,
    folder_path: str | None,
) -> bool:
    """폴더·파일 이름에 모자이크 파괴(모파) 키워드가 있으면 True."""
    for text in _collect_path_texts(video_path, folder_path):
        if _MOPA_NAME_RE.search(text):
            return True
    return False
