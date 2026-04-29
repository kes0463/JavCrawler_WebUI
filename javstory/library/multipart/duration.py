"""영상 길이(초) — ffprobe(ffmpeg-python)."""

from __future__ import annotations

from pathlib import Path


def probe_video_duration_seconds(path: Path | str) -> float:
    """컨테이너 기준 재생 길이(초). 실패 시 OSError."""
    import ffmpeg

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    info = ffmpeg.probe(str(p))
    dur = info.get("format", {}).get("duration")
    if dur is None:
        raise ValueError(f"duration 필드 없음: {p}")
    return float(dur)
