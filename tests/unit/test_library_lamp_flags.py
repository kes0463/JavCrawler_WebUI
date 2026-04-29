"""library_data 램프 규칙(STT / Subtitle / 자체자막)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gui.library_data import (
    compute_library_lamp_flags,
    file_rule_lamp_stt_sub,
    path_contains_self_subtitle_marker,
)


@pytest.mark.parametrize(
    "ja,ko,pl,expect",
    [
        (True, True, False, (True, True)),
        (True, False, False, (True, False)),
        (False, True, False, (False, True)),
        (False, False, True, (False, True)),
        (False, False, False, (False, False)),
        (True, True, True, (True, True)),
        (True, False, True, (True, False)),
    ],
)
def test_file_rule_lamp_stt_sub(ja: bool, ko: bool, pl: bool, expect: tuple[bool, bool]) -> None:
    assert file_rule_lamp_stt_sub(ja, ko, pl) == expect


def test_self_subtitle_marker_in_folder_name(tmp_path: Path) -> None:
    folder = tmp_path / "내_자체자막_폴더"
    folder.mkdir()
    video = folder / "movie.mp4"
    video.write_bytes(b"x")
    assert path_contains_self_subtitle_marker(video, str(folder))


def test_plain_bracket_subtitle_tag_not_self_sub(tmp_path: Path) -> None:
    """`[자막]` 만 있는 파일명은 자체자막 마커가 아님."""
    folder = tmp_path / "배우별"
    folder.mkdir()
    video = folder / "[자막] ABC-001.mp4"
    video.write_bytes(b"x")
    assert not path_contains_self_subtitle_marker(video, str(folder))


def test_self_subtitle_space_variant(tmp_path: Path) -> None:
    folder = tmp_path / "작품 [자체 자막]"
    folder.mkdir()
    video = folder / "x.mp4"
    video.write_bytes(b"x")
    assert path_contains_self_subtitle_marker(video, str(folder))


def test_marker_short_circuits_other_lamps(tmp_path: Path) -> None:
    folder = tmp_path / "자체자막_pack"
    folder.mkdir()
    video = folder / "ABC-001.mp4"
    video.write_bytes(b"x")
    (folder / "ABC-001.ja.srt").write_text("1\n", encoding="utf-8")
    (folder / "ABC-001.ko.srt").write_text("2\n", encoding="utf-8")
    stt, sub, hc = compute_library_lamp_flags(
        product_code="ABC-001",
        video_path=video,
        folder_path=str(folder),
        db_is_hardcoded=False,
    )
    assert (stt, sub, hc) == (False, False, True)


def test_sidecar_ja_only(tmp_path: Path) -> None:
    video = tmp_path / "FOO-100.mp4"
    video.write_bytes(b"x")
    (tmp_path / "FOO-100.ja.srt").write_text("s\n", encoding="utf-8")
    stt, sub, hc = compute_library_lamp_flags(
        product_code="FOO-100",
        video_path=video,
        folder_path=str(tmp_path),
        db_is_hardcoded=False,
    )
    assert (stt, sub, hc) == (True, False, False)


def test_sidecar_plain_only(tmp_path: Path) -> None:
    video = tmp_path / "BAR-200.mp4"
    video.write_bytes(b"x")
    (tmp_path / "BAR-200.srt").write_text("s\n", encoding="utf-8")
    stt, sub, hc = compute_library_lamp_flags(
        product_code="BAR-200",
        video_path=video,
        folder_path=str(tmp_path),
        db_is_hardcoded=False,
    )
    assert (stt, sub, hc) == (False, True, False)
