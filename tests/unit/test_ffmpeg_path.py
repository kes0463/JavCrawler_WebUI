"""ffmpeg_path 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from javstory.utils.ffmpeg_path import path_for_ffmpeg


def test_path_for_ffmpeg_brackets_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("javstory.utils.ffmpeg_path.os.name", "nt")
    p = Path(r"F:\folder\[Actress] CODE-001\video.mp4")
    out = path_for_ffmpeg(p)
    assert out.startswith("\\\\?\\")
    assert "CODE-001" in out


def test_path_for_ffmpeg_leading_dash_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("javstory.utils.ffmpeg_path.os.name", "nt")
    p = Path(r"F:\folder\- [Actress] CODE-001.mp4")
    out = path_for_ffmpeg(p)
    assert out.startswith("\\\\?\\")
    assert "- [Actress]" in out
    assert not out.startswith("file:")


def test_path_for_ffmpeg_output_plain_on_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("javstory.utils.ffmpeg_path.os.name", "nt")
    out = tmp_path / "preview_montage_abc.mp4"
    out.write_bytes(b"x")
    assert path_for_ffmpeg(out, output=True) == str(out.resolve())
    assert not path_for_ffmpeg(out, output=True).startswith("\\\\?\\")


def test_path_for_ffmpeg_plain_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("javstory.utils.ffmpeg_path.os.name", "nt")
    p = Path(r"F:\folder\video.mp4")
    out = path_for_ffmpeg(p)
    assert not out.startswith("\\\\?\\") or len(out) < 240
