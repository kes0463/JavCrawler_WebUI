"""파트별 SRT를 오프셋 합산해 하나의 논리 타임라인 SRT로 병합."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pysrt


def cumulative_offsets_sec(part_durations_sec: list[float]) -> list[float]:
    """각 파트 시작 시각(초) — 파트0는 0, 파트1은 앞 구간 길이 합."""
    out: list[float] = []
    acc = 0.0
    for d in part_durations_sec:
        out.append(acc)
        acc += max(0.0, float(d))
    return out


def sibling_srt_for_video(video: Path) -> Path | None:
    """동일 베이스명 `.ja.srt` 우선, 없으면 `.srt`."""
    ja = video.with_suffix(".ja.srt")
    if ja.is_file():
        return ja
    plain = video.with_suffix(".srt")
    if plain.is_file():
        return plain
    return None


def merge_part_srts_to_logical_timeline(
    ordered_videos: list[Path],
    out_srt: Path,
    *,
    encoding: str = "utf-8",
) -> tuple[bool, str]:
    """
    각 영상 옆 파트 SRT를 읽어, 앞선 파트들의 재생 길이만큼 시간 이동 후 한 파일로 저장.
    플레이어용이 아니라 번역·전체 타임라인 참고용(합본).
    """
    if len(ordered_videos) < 2:
        return False, "영상 경로가 2개 미만입니다."

    from javstory.library.multipart.duration import probe_video_duration_seconds

    durations: list[float] = []
    srt_paths: list[Path] = []
    for v in ordered_videos:
        try:
            durations.append(probe_video_duration_seconds(v))
        except Exception as e:
            return False, f"길이 확인 실패 ({v.name}): {e}"
        sp = sibling_srt_for_video(v)
        if sp is None:
            return False, f"자막 없음 (동명 .ja.srt 또는 .srt): {v.name}"
        srt_paths.append(sp)

    offsets = cumulative_offsets_sec(durations)
    merged: list = []
    for srt_path, off in zip(srt_paths, offsets):
        subs = pysrt.open(str(srt_path), encoding=encoding)
        for sub in subs:
            item = deepcopy(sub)
            if off:
                item.shift(seconds=off)
            merged.append(item)

    merged.sort(key=lambda s: s.start.ordinal)
    for i, sub in enumerate(merged, start=1):
        sub.index = i

    out_srt.parent.mkdir(parents=True, exist_ok=True)
    pysrt.SubRipFile(merged).save(str(out_srt), encoding=encoding)
    return True, f"저장: {out_srt}"
