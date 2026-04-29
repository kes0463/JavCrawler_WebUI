"""Transcription 작업 큐 — 동영상 확장자·폴더(비재귀)·경로 정규화."""

from __future__ import annotations

from pathlib import Path

from javstory.library.video_ext import is_video_file


def collect_videos_flat_folder(folder: Path) -> list[Path]:
    """폴더 **바로 아래** 동영상만 (하위 폴더 재귀 없음)."""
    if not folder.is_dir():
        return []
    out: list[Path] = []
    try:
        for child in folder.iterdir():
            if child.is_file() and is_video_file(child):
                out.append(child)
    except OSError:
        return []
    out.sort(key=lambda p: p.name.lower())
    return out


def normalize_unique_paths(paths: list[str | Path]) -> list[Path]:
    """절대 경로 resolve 후 중복 제거(입력 순서 유지)."""
    seen: set[str] = set()
    out: list[Path] = []
    for raw in paths:
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
