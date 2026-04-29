"""멀티파트 작업 — 정렬·길이·합본 SRT 한 번에."""

from __future__ import annotations

from pathlib import Path

from javstory.library.multipart.detect import sort_video_parts, suggest_groups_in_directories
from javstory.library.multipart.srt_timeline import merge_part_srts_to_logical_timeline


def prepare_ordered_videos(paths: list[Path]) -> list[Path]:
    """파일명 파트 규칙으로 순서 정렬."""
    return sort_video_parts([p.resolve() for p in paths if p.is_file()])


def build_logical_merged_srt(
    video_paths: list[Path],
    output_path: Path,
) -> tuple[bool, str]:
    """
    파트별 동명 SRT(이미 STT 등으로 생성됨)를 합쳐 논리 타임라인 SRT 생성.
    `output_path` 예: `{품번}_merged_logic.ja.srt`
    """
    ordered = prepare_ordered_videos(video_paths)
    return merge_part_srts_to_logical_timeline(ordered, output_path)


__all__ = [
    "prepare_ordered_videos",
    "build_logical_merged_srt",
    "suggest_groups_in_directories",
]
