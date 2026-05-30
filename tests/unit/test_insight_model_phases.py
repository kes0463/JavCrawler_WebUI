"""InsightModel 단계별 refresh·persona cache_only."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_get_persona_card_cache_only_skips_synthesis(tmp_path, monkeypatch):
    from javstory.analytics import persona_card as pc

    cache_path = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_path)

    # 캐시 없음 → 빈 페르소나
    out = pc.get_persona_card(cache_only=True)
    assert out.get("summary") == ""
    assert out.get("source") == "none"

    # 유효한 캐시 → 정상 반환
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "persona_type": "탐색형",
                "summary": "캐시됨",
                "generated_at": "2099-01-01T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out2 = pc.get_persona_card(cache_only=True)
    assert out2.get("summary") == "캐시됨"
    assert out2.get("source") == "cache"


def test_get_persona_card_cache_only_stale_fallback(tmp_path, monkeypatch):
    """방안 B: cache_only=True 일 때 만료 캐시도 빈 페르소나 대신 stale로 반환한다."""
    from javstory.analytics import persona_card as pc

    cache_path = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_path)

    # 만료된 캐시 (generated_at 이 과거)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "persona_type": "검증형",
                "summary": "오래된 캐시",
                "generated_at": "2000-01-01T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = pc.get_persona_card(cache_only=True)
    # 빈 페르소나가 아니라 stale 데이터 반환
    assert out.get("summary") == "오래된 캐시"
    assert out.get("source") == "cache_stale"
    assert out.get("stale") is True


def test_erotic_persona_engine_skip_context_independent_of_cache_only():
    """방안 A: skip_context 가 False(기본) 이면 cache_only=True 여도 context_snapshot() 이 호출된다."""
    from unittest.mock import MagicMock, patch

    from javstory.persona.erotic_persona_engine import EroticPersonaEngine

    engine = EroticPersonaEngine(cache_only=True, skip_context=False)
    dummy_context = {"top_actors": [{"name": "테스트배우", "count": 5}], "top_genres": []}

    with patch.object(engine, "context_snapshot", return_value=dummy_context) as mock_ctx, \
         patch.object(engine, "persona_snapshot", return_value={"summary": "", "source": "none",
                                                                  "persona_type": "", "sensual_summary": "",
                                                                  "turn_ons": [], "avoidances": [],
                                                                  "affinities": [], "evidence": []}), \
         patch("javstory.persona.erotic_persona_engine._top_strong_reactions", return_value=[]), \
         patch("javstory.persona.erotic_persona_engine.HybridLibrarySearch") as mock_search:
        mock_search.return_value.search_with_fusion.return_value = []
        result = engine.build_chat_context("일반 대화")

    mock_ctx.assert_called_once()  # cache_only=True 여도 context_snapshot() 호출됨
    assert result["taste_context"]["top_actors"] == [{"name": "테스트배우", "count": 5}]


def test_erotic_persona_engine_skip_context_true_skips_db():
    """방안 A: skip_context=True 이면 context_snapshot() 이 호출되지 않고 taste_context 가 비어있다."""
    from unittest.mock import patch

    from javstory.persona.erotic_persona_engine import EroticPersonaEngine

    engine = EroticPersonaEngine(cache_only=True, skip_context=True)

    with patch.object(engine, "context_snapshot") as mock_ctx, \
         patch.object(engine, "persona_snapshot", return_value={"summary": "", "source": "none",
                                                                  "persona_type": "", "sensual_summary": "",
                                                                  "turn_ons": [], "avoidances": [],
                                                                  "affinities": [], "evidence": []}), \
         patch("javstory.persona.erotic_persona_engine._top_strong_reactions", return_value=[]), \
         patch("javstory.persona.erotic_persona_engine.HybridLibrarySearch") as mock_search:
        mock_search.return_value.search_with_fusion.return_value = []
        result = engine.build_chat_context("일반 대화")

    mock_ctx.assert_not_called()  # skip_context=True → context_snapshot() 생략
    assert result["taste_context"]["top_actors"] == []


def test_insight_fetch_core_uses_cache_only_persona(monkeypatch):
    from gui.models.insight_model import InsightModel

    monkeypatch.setenv("JAVSTORY_PERSONA_DEEP_ENABLED", "0")
    with patch.object(InsightModel, "_excluded_genres", return_value=set()):
        with patch(
            "javstory.analytics.persona_card.get_persona_card",
            side_effect=lambda **kw: {"summary": "x", "cache_only": kw.get("cache_only")},
        ) as mock_persona:
            InsightModel._fetch_phase(InsightModel._PHASE_CORE)
            mock_persona.assert_called_once_with(cache_only=True)


def test_persona_feedback_persists_jsonl(tmp_path, monkeypatch):
    import javstory.config.app_config as app_config
    from gui.models.insight_model import InsightModel

    monkeypatch.setattr(app_config, "DATA_ROOT", tmp_path)
    InsightModel._persist_persona_feedback(
        "positive",
        {
            "persona_type": "검증형",
            "summary": "요약",
            "input_fingerprint": "abc",
            "semantic_fingerprint": "def",
            "generated_at": "2099-01-01T00:00:00",
            "source": "test",
        },
    )

    path = tmp_path / "cache" / "persona_feedback.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["feedback"] == "positive"
    assert rows[0]["persona_type"] == "검증형"
    assert rows[0]["input_fingerprint"] == "abc"


def test_library_distribution_cache_short_circuit():
    from unittest.mock import patch
    import time

    from javstory.analytics import library_stats as ls

    sentinel = {"actors": [{"name": "cached", "count": 1}], "genres": [], "makers": []}
    ls._DIST_CACHE = (time.time(), sentinel)
    with patch("javstory.analytics.library_stats.get_db_session_ctx") as mock_ctx:
        assert ls.get_library_distribution() is sentinel
        mock_ctx.assert_not_called()
    ls._DIST_CACHE = None
