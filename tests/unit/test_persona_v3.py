"""페르소나 v3 — 컨텍스트·합성·캐시."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_build_persona_context_empty_db():
    from javstory.analytics.persona_context import build_persona_context

    ctx = build_persona_context(max_products=4)
    assert "stats" in ctx
    assert "coverage" in ctx
    assert isinstance(ctx["tag_counter"], list)


def test_extract_grok_tags_in_context(monkeypatch):
    from javstory.analytics import persona_context as pc

    monkeypatch.setattr(pc, "_sample_product_codes", lambda n: ["ABC-123"])
    monkeypatch.setattr(pc, "_watch_meta_by_codes", lambda codes: {"ABC-123": {}})
    monkeypatch.setattr(pc, "_find_srt_paths", lambda *a, **k: [])

    grok_data = {
        "verification_ok": True,
        "overall_summary": "테스트 요약",
        "scenes": [{"tone": "밝은 분위기", "key_tags": ["footjob", "edging"]}],
    }

    with patch(
        "javstory.translation.story_grok_module.load_cached_grok_json_flexible",
        return_value=grok_data,
    ):
        with patch("javstory.library.paths.library_state_path", return_value=Path("/no/such/file.json")):
            ctx = pc.build_persona_context(max_products=1)

    assert ctx["coverage"]["grok"] >= 1
    names = [t["name"] for t in ctx["tag_counter"]]
    assert "footjob" in names or "edging" in names


def test_synthesize_fallback_without_ollama():
    from javstory.analytics.persona_card import synthesize_persona_v3, _SCHEMA_VERSION

    ctx = {
        "drift_hint": "최근 장르 이동",
        "tag_counter": [{"name": "drama", "count": 3}],
        "coverage": {"grok": 1, "canonical": 0, "subtitle": 0},
        "stats": {"total": 10},
        "samples": [],
    }

    with patch("httpx.post", side_effect=OSError("offline")):
        payload = synthesize_persona_v3(ctx)

    assert payload["schema_version"] == _SCHEMA_VERSION
    assert payload["persona_type"]
    assert payload["summary"]
    assert payload["source"] == "fallback"


def test_get_persona_card_cache(tmp_path, monkeypatch):
    from javstory.analytics import persona_card as pc

    cache_file = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_file)
    payload = {
        "schema_version": 2,
        "persona_type": "테스트형",
        "summary": "캐시 본문",
        "generated_at": "2099-01-01T00:00:00",
        "source": "ollama",
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    out = pc.get_persona_card(force_refresh=False)
    assert out["persona_type"] == "테스트형"
    assert out["summary"] == "캐시 본문"
    assert out["source"] == "cache"


def test_persona_deep_disabled(monkeypatch):
    from javstory.analytics.persona_context import build_persona_context, persona_deep_enabled

    monkeypatch.setenv("JAVSTORY_PERSONA_DEEP_ENABLED", "0")
    assert persona_deep_enabled() is False
    ctx = build_persona_context()
    assert ctx["samples"] == []
    assert ctx["coverage"]["grok"] == 0
