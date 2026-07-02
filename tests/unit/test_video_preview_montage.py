"""video_preview 몽타주 유틸 테스트."""

from __future__ import annotations

from javstory.library.highlight.video_preview import (
    _extract_segment_mp4,
    _validate_montage_duration,
    compute_montage_segments,
    resolve_preview_media_type,
)


def test_compute_montage_segments_default_ten_by_two() -> None:
    segs = compute_montage_segments(3600.0)
    assert len(segs) == 10
    assert abs(sum(s[1] for s in segs) - 20.0) < 0.01


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


def test_extract_segment_mp4_uses_fast_seek_by_default(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._ffprobe_duration_sec",
        lambda _p: 3.0,
    )
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._preview_use_nvenc",
        lambda: False,
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
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert ss_idx < i_idx


def test_extract_segment_mp4_prefers_nvenc_when_enabled(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._ffprobe_duration_sec",
        lambda _p: 2.0,
    )
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview._preview_use_nvenc",
        lambda: True,
    )

    rc, _ = _extract_segment_mp4(
        src=src,
        out=out,
        start=1.0,
        seg_len=2.0,
        crf=28,
        threads=2,
    )
    assert rc == 0
    assert "h264_nvenc" in captured[0]


def test_resolve_preview_media_type_prefers_mp4_montage_over_legacy_webp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    preview_dir = tmp_path / "AAA-001" / "Preview"
    preview_dir.mkdir(parents=True)
    webp = preview_dir / "preview.webp"
    mp4 = preview_dir / "preview.mp4"
    meta = preview_dir / "preview.webp.meta.json"
    webp.write_bytes(b"legacy-webp")
    mp4.write_bytes(b"x" * 200_000)
    meta.write_text(
        '{"version":1,"params":{"montage":"10x2.0@segment-ss-mp4","seed":0,"skip_webp":true}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "javstory.library.highlight.video_preview.is_montage_preview_fresh",
        lambda **_kwargs: False,
    )

    assert resolve_preview_media_type(webp) == "mp4"
