"""Grok 스토리 캐시 경로·이관·레거시 읽기 폴백."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import javstory.translation.story_grok_module as grok_mod
from javstory.translation.story_grok_module import (
    has_disk_grok_story_cache,
    load_cached_grok_json_flexible,
    migrate_story_context_cache_files,
    story_context_cache_path_grok,
    story_context_legacy_cache_dir,
)


@pytest.fixture(autouse=True)
def _reset_story_cache_migration_flag() -> None:
    grok_mod._story_cache_migrated = False
    yield
    grok_mod._story_cache_migrated = False


@pytest.fixture
def grok_cache_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    primary = tmp_path / "story_context"
    legacy = tmp_path / "legacy_story_context"
    primary.mkdir(parents=True)
    legacy.mkdir(parents=True)
    monkeypatch.setattr(grok_mod, "_LEGACY_STORY_CONTEXT_CACHE_DIR", legacy)
    monkeypatch.setattr(
        "javstory.config.app_config.STORY_CONTEXT_CACHE_DIR",
        primary,
    )
    return primary, legacy


def test_story_context_cache_path_grok_normalizes_folder_suffix(
    grok_cache_dirs: tuple[Path, Path],
) -> None:
    primary, _ = grok_cache_dirs
    path = story_context_cache_path_grok("ABW-358__HD__A")
    assert path.parent == primary
    assert path.name == "ABW-358_grok.json"


def test_migrate_story_context_cache_files_copies_newer_legacy(
    grok_cache_dirs: tuple[Path, Path],
) -> None:
    primary, legacy = grok_cache_dirs
    payload = {"product_code": "ABW-358", "schema_version": 1}
    legacy_file = legacy / "ABW-358_grok.json"
    legacy_file.write_text(json.dumps(payload), encoding="utf-8")

    stats = migrate_story_context_cache_files()
    assert stats["copied"] == 1
    dst = primary / "ABW-358_grok.json"
    assert dst.is_file()
    assert json.loads(dst.read_text(encoding="utf-8"))["product_code"] == "ABW-358"


def test_load_cached_grok_json_flexible_legacy_fallback(
    grok_cache_dirs: tuple[Path, Path],
) -> None:
    _, legacy = grok_cache_dirs
    data = {"product_code": "MIUM-123", "title_ko": "테스트"}
    (legacy / "MIUM-123_grok.json").write_text(json.dumps(data), encoding="utf-8")

    got = load_cached_grok_json_flexible("MIUM-123")
    assert got is not None
    assert got.get("product_code") == "MIUM-123"
    assert got.get("title_ko") == "테스트"


def test_has_disk_grok_story_cache_primary_and_legacy(
    grok_cache_dirs: tuple[Path, Path],
) -> None:
    primary, legacy = grok_cache_dirs
    assert has_disk_grok_story_cache("ZZZ-999") is False
    (primary / "ZZZ-999_grok.json").write_text("{}", encoding="utf-8")
    assert has_disk_grok_story_cache("ZZZ-999") is True
    (primary / "ZZZ-999_grok.json").unlink()
    (legacy / "ZZZ-999_grok.json").write_text("{}", encoding="utf-8")
    assert has_disk_grok_story_cache("ZZZ-999") is True
    assert story_context_legacy_cache_dir() == legacy
