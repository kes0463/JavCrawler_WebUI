"""cover_upload 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from javstory.library.cover_upload import save_cover_image


def test_save_cover_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        save_cover_image("TST-001", tmp_path / "nope.jpg")


def test_save_cover_image_rejects_bad_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_MEDIA_ROOT", str(tmp_path / "media"))
    bad = tmp_path / "x.txt"
    bad.write_text("not image", encoding="utf-8")
    with pytest.raises(ValueError, match="지원 형식"):
        save_cover_image("TST-001", bad)


def test_save_cover_image_writes_poster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_MEDIA_ROOT", str(tmp_path / "media"))
    src = tmp_path / "src.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    poster = save_cover_image("TST-002", src)
    assert poster.name == "poster.jpg"
    assert poster.is_file()
    assert (poster.parent / "cover.jpg").is_file()
    assert (poster.parent / "thumb.jpg").is_file()
