"""Unit tests for harvest_execution_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from javstory.services.harvest_execution_service import HarvestEntry, resolve_sku, run_one_sync


def test_resolve_sku_code_only():
    entry = HarvestEntry(target="STARS-001", is_path=False)
    assert resolve_sku(entry) == "STARS-001"


def _patch_run_one_deps(monkeypatch, fake_crawler):
    mock_translator = MagicMock()
    mock_translator.close = AsyncMock()
    monkeypatch.setattr("javstory.harvest.coordinator.run_crawler_for_video_path", fake_crawler)
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)
    monkeypatch.setattr("javstory.harvest.translator.MetadataTranslator", lambda: mock_translator)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def query(self, *_):
            return self

        def filter_by(self, **_):
            return self

        def first(self):
            return None

    monkeypatch.setattr("javstory.harvest.database.get_db_session_ctx", lambda: FakeSession())


def test_run_one_sync_success(monkeypatch):
    async def fake_crawler(*_a, **kwargs):
        cb = kwargs.get("progress_cb")
        if cb:
            cb("STARS-001", "크롤링...", 25)
        assert kwargs.get("skip_translation") is False  # Qt 큐 없음 → 인라인 번역
        return {"error": None}

    _patch_run_one_deps(monkeypatch, fake_crawler)
    monkeypatch.setattr(
        "javstory.services.harvest_execution_service._translation_queue_available",
        lambda: False,
    )
    progress: list[tuple[str, str, int]] = []

    result = run_one_sync(
        HarvestEntry(target="STARS-001", product_code="STARS-001"),
        grok_enabled=False,
        on_progress=lambda s, m, p: progress.append((s, m, p)),
    )

    assert result["ok"] is True
    assert result["sku"] == "STARS-001"
    assert any(p[2] == 100 for p in progress)


def test_run_one_sync_crawler_error(monkeypatch):
    async def fake_crawler(*_a, **_kw):
        return {"error": "not found", "skeleton_saved": False}

    _patch_run_one_deps(monkeypatch, fake_crawler)
    result = run_one_sync(HarvestEntry(target="BAD-000", product_code="BAD-000"))
    assert result["ok"] is False
    assert "not found" in result["message"]
