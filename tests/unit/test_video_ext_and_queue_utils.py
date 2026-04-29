"""동영상 확장자 판별."""

from __future__ import annotations

from pathlib import Path

from javstory.library.video_ext import VIDEO_EXT_SET, is_video_file


def test_video_ext_set_includes_common() -> None:
    assert ".mp4" in VIDEO_EXT_SET
    assert ".m4v" in VIDEO_EXT_SET


def test_is_video_file_tmp(tmp_path: Path) -> None:
    v = tmp_path / "clip.mp4"
    v.write_bytes(b"")
    assert is_video_file(v) is True
    t = tmp_path / "readme.txt"
    t.write_text("x")
    assert is_video_file(t) is False
