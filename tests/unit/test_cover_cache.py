"""javstory.library.cover_cache 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from javstory.library.cover_cache import cover_needs_download, resolve_cover_path


def test_resolve_cover_prefers_existing_local(tmp_path: Path) -> None:
    p = tmp_path / "x.jpg"
    p.write_bytes(b"x")
    r = resolve_cover_path("ABC-001", str(p))
    assert r == p.resolve()


def test_resolve_cover_finds_media_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from javstory.config import app_config

    root_media = tmp_path / "mediaroot"
    media = root_media / "ABC-002"
    media.mkdir(parents=True)
    cover = media / "cover.jpg"
    cover.write_bytes(b"jpeg")
    monkeypatch.setattr(app_config, "MEDIA_ROOT", root_media)
    r = resolve_cover_path("ABC-002", None)
    assert r == cover.resolve()


def test_resolve_cover_finds_works_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """data/works/{품번}/cover.jpg — E_MEDIA_ROOT."""
    from javstory.config import app_config

    root_works = tmp_path / "worksroot"
    w = root_works / "XYZ-100"
    w.mkdir(parents=True)
    cover = w / "cover.jpg"
    cover.write_bytes(b"jpeg")
    monkeypatch.setattr(app_config, "E_MEDIA_ROOT", root_works)
    monkeypatch.setattr(app_config, "MEDIA_ROOT", tmp_path / "empty_media")
    r = resolve_cover_path("XYZ-100", None)
    assert r == cover.resolve()


def test_cover_needs_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from javstory.config import app_config

    root_media = tmp_path / "mediaroot"
    monkeypatch.setattr(app_config, "MEDIA_ROOT", root_media)
    assert cover_needs_download("XYZ-999", "https://example.com/c.jpg", None) is True
    (root_media / "XYZ-999").mkdir(parents=True)
    (root_media / "XYZ-999" / "cover.jpg").write_bytes(b"1")
    assert cover_needs_download("XYZ-999", "https://example.com/c.jpg", None) is False
