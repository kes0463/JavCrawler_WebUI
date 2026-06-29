"""video_preview 몽타주 유틸 테스트."""

from __future__ import annotations

from javstory.library.highlight.video_preview import (
    _extract_segment_mp4,
    _validate_montage_duration,
    compute_montage_segments,
)


def test_compute_montage_segments_full_length() -> None:
    segs = compute_montage_segments(3600.0, segment_count=10, segment_sec=3.0)
    assert len(segs) == 10
    assert abs(sum(s[1] for s in segs) - 30.0) < 0.01


def test_validate_montage_duration_threshold(monkeypatch, tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"x" * 1024)
    segments = [(0.0, 3.0)] * 10

    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._ffprobe_duration_sec",
        lambda _p: 26.0,
    )
    assert _validate_montage_duration(out, segments) is True

    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._ffprobe_duration_sec",
        lambda _p: 17.0,
    )
    out.write_bytes(b"x" * 200_000)
    assert _validate_montage_duration(out, segments) is True

    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._ffprobe_duration_sec",
        lambda _p: 8.0,
    )
    assert _validate_montage_duration(out, segments) is False


def test_extract_segment_mp4_uses_accurate_seek_by_default(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    src.write_bytes(b"x")
    out = tmp_path / "seg.mp4"
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        out.write_bytes(b"mp4")
        class R:
            returncode = 0
            stderr = b""
        return R()

    monkeypatch.setattr(
        "javstory.library.highlight.video_preview.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview.get_ffmpeg",
        lambda: "ffmpeg",
    )

    rc, _ = _extract_segment_mp4(
        src=src,
        out=out,
        start=12.5,
        seg_len=3.0,
        crf=28,
        threads=2,
    )
    assert rc == 0
    cmd = captured[0]
    assert "-ignore_editlist" not in cmd
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert ss_idx > i_idx
