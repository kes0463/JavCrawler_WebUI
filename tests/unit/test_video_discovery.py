"""video_discovery — 품번 기반 로컬 영상 탐색."""

from __future__ import annotations

from pathlib import Path

from javstory.library.video_discovery import (
    find_all_video_paths_for_product,
    scan_videos_in_dir,
)


def test_scan_videos_in_dir_finds_nested(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    v = sub / "clip.mp4"
    v.write_bytes(b"x")
    found = scan_videos_in_dir(tmp_path)
    assert v in found


def test_find_all_video_paths_filters_by_product_code(tmp_path: Path, monkeypatch) -> None:
    bind = tmp_path / "bind"
    bind.mkdir()
    match = bind / "ABC-123_part1.mp4"
    other = bind / "XYZ-999.mp4"
    match.write_bytes(b"1")
    other.write_bytes(b"2")

    def fake_search_dirs(pc: str, folder_path: str | None = None) -> list[Path]:
        return [Path(folder_path)] if folder_path else []

    monkeypatch.setattr(
        "javstory.library.video_discovery.video_search_dirs",
        fake_search_dirs,
    )
    paths = find_all_video_paths_for_product("ABC-123", str(bind))
    assert paths == [match]
