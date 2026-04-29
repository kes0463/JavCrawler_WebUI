"""멀티파트 정렬·타임라인 오프셋·합본 SRT (ffprobe 목)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from javstory.library.multipart.detect import sort_video_parts
from javstory.library.multipart.pipeline import prepare_ordered_videos
from javstory.library.multipart.srt_timeline import (
    cumulative_offsets_sec,
    merge_part_srts_to_logical_timeline,
)


def test_cumulative_offsets_sec() -> None:
    assert cumulative_offsets_sec([10.0, 20.0, 5.0]) == [0.0, 10.0, 30.0]


def test_sort_video_parts_by_part_number(tmp_path: Path) -> None:
    a = tmp_path / "foo_part2.mp4"
    b = tmp_path / "foo_part1.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    out = sort_video_parts([a, b])
    assert [p.name for p in out] == ["foo_part1.mp4", "foo_part2.mp4"]


def test_prepare_ordered_videos_filters_dirs(tmp_path: Path) -> None:
    f = tmp_path / "p_part1.mp4"
    f.write_bytes(b"x")
    assert len(prepare_ordered_videos([f, tmp_path])) == 1


def test_merge_part_srts_logical_timeline_mocked_duration(tmp_path: Path) -> None:
    v1 = tmp_path / "m_part1.mp4"
    v2 = tmp_path / "m_part2.mp4"
    v1.write_bytes(b"v")
    v2.write_bytes(b"v")
    s1 = v1.with_suffix(".ja.srt")
    s2 = v2.with_suffix(".ja.srt")
    s1.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nA\n\n",
        encoding="utf-8",
    )
    s2.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nB\n\n",
        encoding="utf-8",
    )
    out_srt = tmp_path / "merged.ja.srt"
    with patch(
        "javstory.library.multipart.duration.probe_video_duration_seconds",
        side_effect=[10.0, 20.0],
    ):
        ok, msg = merge_part_srts_to_logical_timeline([v1, v2], out_srt)
    assert ok is True
    assert out_srt.is_file()
    text = out_srt.read_text(encoding="utf-8")
    assert "A" in text and "B" in text
