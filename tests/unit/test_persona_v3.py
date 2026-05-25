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

    monkeypatch.setattr(
        pc,
        "_sample_product_groups",
        lambda n: {
            "positive": ["ABC-123"],
            "recent": ["ABC-123"],
            "long_term": [],
            "negative": [],
            "codes": ["ABC-123"],
        },
    )
    monkeypatch.setattr(pc, "_build_semantic_profile", lambda *a, **k: {})
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


def test_persona_context_recent_window_env(monkeypatch):
    from javstory.analytics import persona_context as pc

    monkeypatch.setenv("JAVSTORY_PERSONA_DEEP_ENABLED", "0")
    monkeypatch.setenv("JAVSTORY_PERSONA_RECENT_DAYS", "14")
    monkeypatch.setenv("JAVSTORY_PERSONA_SHORT_RECENT_DAYS", "3")
    monkeypatch.setattr(pc, "get_library_stats", lambda: {})
    monkeypatch.setattr(pc, "compute_taste_vector", lambda: {"axes": []})
    monkeypatch.setattr(pc, "get_monthly_genre_trend", lambda n: [{"genres": [{"name": "장기"}]}])
    monkeypatch.setattr(pc, "get_top_actors", lambda *a, **k: [])
    monkeypatch.setattr(pc, "get_top_genres", lambda *a, **k: [])
    monkeypatch.setattr(
        pc,
        "compute_recent_trend",
        lambda days, excluded_genres=None: {
            "actors": [],
            "genres": [{"name": f"{days}일", "score": 1, "recent_score": 1}],
        },
    )

    ctx = pc.build_persona_context()

    assert ctx["recent_window"] == {"short_days": 3, "days": 14}
    assert "3일" in ctx["drift_hint"]
    assert "14일" in ctx["drift_hint"]


def test_grok_cache_failure_does_not_break_context(monkeypatch):
    from javstory.analytics import persona_context as pc

    monkeypatch.setattr(pc, "get_library_stats", lambda: {})
    monkeypatch.setattr(pc, "compute_taste_vector", lambda: {"axes": []})
    monkeypatch.setattr(pc, "get_monthly_genre_trend", lambda n: [])
    monkeypatch.setattr(pc, "get_top_actors", lambda *a, **k: [])
    monkeypatch.setattr(pc, "get_top_genres", lambda *a, **k: [])
    monkeypatch.setattr(pc, "compute_recent_trend", lambda *a, **k: {"actors": [], "genres": []})
    monkeypatch.setattr(
        pc,
        "_sample_product_groups",
        lambda n: {
            "positive": ["ABC-123"],
            "recent": ["ABC-123"],
            "long_term": [],
            "negative": [],
            "codes": ["ABC-123"],
        },
    )
    monkeypatch.setattr(pc, "_build_semantic_profile", lambda *a, **k: {})
    monkeypatch.setattr(pc, "_watch_meta_by_codes", lambda codes: {"ABC-123": {}})
    monkeypatch.setattr(pc, "_find_srt_paths", lambda *a, **k: [])

    with patch(
        "javstory.translation.story_grok_module.load_cached_grok_json_flexible",
        side_effect=OSError("broken cache"),
    ):
        with patch("javstory.library.paths.library_state_path", return_value=Path("/no/such/file.json")):
            ctx = pc.build_persona_context(max_products=1)

    assert ctx["coverage"]["grok"] == 0
    assert ctx["coverage"]["grok_errors"] == 1
    assert ctx["samples"][0]["grok_error"] == "OSError"


def test_persona_prompt_budget_limits_samples(monkeypatch):
    from javstory.analytics.persona_card import _context_for_prompt

    monkeypatch.setenv("JAVSTORY_PERSONA_PROMPT_SAMPLES", "1")
    monkeypatch.setenv("JAVSTORY_PERSONA_PROMPT_GROK_SUMMARY_CHARS", "80")
    monkeypatch.setenv("JAVSTORY_PERSONA_PROMPT_SAMPLE_TAGS", "1")

    payload = json.loads(_context_for_prompt({
        "samples": [
            {
                "product_code": "ABC-123",
                "grok": {"overall_summary": "가" * 120, "tags": ["a", "b"]},
                "canonical": {"tags": ["c", "d"]},
            },
            {"product_code": "DEF-456"},
        ],
        "tag_counter": [{"name": "x", "count": 1}],
        "tone_counter": [{"name": "y", "count": 1}],
    }))

    assert len(payload["samples"]) == 1
    assert len(payload["samples"][0]["grok_summary"]) == 80
    assert payload["samples"][0]["grok_tags"] == ["a"]
    assert payload["samples"][0]["canonical_tags"] == ["c"]


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
        "body": "캐시 본문",
        "generated_at": "2099-01-01T00:00:00",
        "source": "ollama",
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    out = pc.get_persona_card(cache_only=True)
    assert out["persona_type"] == "테스트형"
    assert out["summary"] == "캐시 본문"
    assert out["source"] == "cache"


def test_persona_card_cache_invalidates_on_fingerprint_change(tmp_path, monkeypatch):
    from javstory.analytics import persona_card as pc

    cache_file = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_file)
    monkeypatch.setattr(pc, "persona_deep_enabled", lambda: True)
    ctx = {
        "stats": {"total": 10, "watched_count": 2, "completed": 1},
        "sample_groups": {"recent": ["NEW-001"]},
        "sample_codes": ["NEW-001"],
        "top_genres": [{"name": "새 장르"}],
        "top_actors": [],
        "tag_counter": [],
        "tone_counter": [],
        "semantic_profile": {},
    }
    monkeypatch.setattr(pc, "build_persona_context", lambda: ctx)
    monkeypatch.setattr(
        pc,
        "synthesize_persona_v3",
        lambda context: pc._normalize_v2_payload(
            {
                "persona_type": "새 타입",
                "summary": "새 페르소나",
                "input_fingerprint": pc._context_fingerprint(context),
                "cache_metrics": pc._context_cache_metrics(context),
            },
            "ollama",
        ),
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "schema_version": 3,
        "persona_type": "구 타입",
        "summary": "오래된 페르소나",
        "input_fingerprint": "stale",
        "cache_metrics": {"total": 10, "watched_count": 2, "completed": 1, "sample_codes": ["OLD-001"]},
        "generated_at": "2099-01-01T00:00:00",
    }), encoding="utf-8")

    out = pc.get_persona_card()

    assert out["summary"] == "새 페르소나"
    assert out["persona_type"] == "새 타입"


def test_persona_card_consistency_removes_conflicting_avoidance():
    from javstory.analytics.persona_card import _normalize_v2_payload

    out = _normalize_v2_payload(
        {
            "persona_type": "검증형",
            "summary": "",
            "sensual_summary": "마사지 텐션을 선호합니다.",
            "turn_ons": ["마사지"],
            "affinities": ["긴장감"],
            "avoidances": ["마사지 싫음", "무맥락 전개"],
            "evidence": [
                {"product_code": "abc-123", "reason": "근거"},
                {"product_code": "ABC-123", "reason": "중복"},
            ],
        },
        "test",
    )

    assert out["summary"] == "마사지 텐션을 선호합니다."
    assert out["avoidances"] == ["무맥락 전개"]
    assert out["evidence"][0]["product_code"] == "ABC-123"
    assert any("removed_conflicting_avoidances" in w for w in out["validation_warnings"])


def test_refresh_persona_semantic_profile_updates_cache_without_llm(tmp_path, monkeypatch):
    from javstory.analytics import persona_card as pc

    cache_file = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_file)
    ctx = {
        "stats": {"total": 10, "watched_count": 2, "completed": 1},
        "sample_groups": {"positive": ["ABC-123"]},
        "sample_codes": ["ABC-123"],
        "top_genres": [],
        "top_actors": [],
        "tag_counter": [],
        "tone_counter": [],
        "semantic_profile": {
            "enabled": True,
            "model": "embed-test",
            "nearest_unwatched": [{"product_code": "NEW-001", "score": 0.9}],
        },
    }
    monkeypatch.setattr(pc, "build_persona_context", lambda: ctx)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "schema_version": 3,
        "persona_type": "기존형",
        "summary": "기존 본문",
        "semantic_profile": {},
        "generated_at": "2099-01-01T00:00:00",
    }), encoding="utf-8")

    out = pc.refresh_persona_semantic_profile()

    assert out["summary"] == "기존 본문"
    assert out["semantic_profile"]["nearest_unwatched"][0]["product_code"] == "NEW-001"
    assert out["embedding_model"] == "embed-test"


def test_persona_context_includes_interaction_signals_in_prompt(tmp_path, monkeypatch):
    import javstory.config.app_config as app_config
    from javstory.analytics import persona_card as pc

    monkeypatch.setattr(app_config, "DATA_ROOT", tmp_path)
    feedback_path = tmp_path / "cache" / "persona_feedback.jsonl"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(
        json.dumps(
            {
                "feedback": "negative",
                "persona_type": "기존형",
                "summary": "기존 요약이 안 맞음",
                "created_at": "2099-01-01T00:00:00",
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    class DummyMemory:
        def prompt_context(self, *_args, **_kwargs):
            return {
                "turn_count": 3,
                "preference_notes": [{"text": "사용자 취향 단서: 어두운 긴장감이 더 좋다"}],
                "strong_reaction_notes": [
                    {"text": "사용자 강렬 반응: AAA-111 좋음", "product_codes": ["AAA-111"]}
                ],
                "negative_feedback_notes": [],
                "correction_notes": [],
            }

    monkeypatch.setattr("javstory.persona.persona_memory.PersonaChatMemory", lambda: DummyMemory())
    ctx = pc._augment_context_with_interaction_signals({"stats": {"total": 1}})
    payload = json.loads(pc._context_for_prompt(ctx))

    assert "interaction_signals" in payload
    assert payload["interaction_signals"]["chat_memory"]["turn_count"] == 3
    assert payload["interaction_signals"]["persona_feedback"]["negative"] == 1
    assert pc._context_fingerprint(ctx) != pc._context_fingerprint({"stats": {"total": 1}})


def test_persona_deep_disabled(monkeypatch):
    from javstory.analytics.persona_context import build_persona_context, persona_deep_enabled

    monkeypatch.setenv("JAVSTORY_PERSONA_DEEP_ENABLED", "0")
    assert persona_deep_enabled() is False
    ctx = build_persona_context()
    assert ctx["samples"] == []
    assert ctx["coverage"]["grok"] == 0
