"""InsightModel 단계별 refresh·persona cache_only."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_get_persona_card_cache_only_skips_synthesis(tmp_path, monkeypatch):
    from javstory.analytics import persona_card as pc

    cache_path = tmp_path / "persona_card.json"
    monkeypatch.setattr(pc, "_CACHE_PATH", cache_path)

    out = pc.get_persona_card(cache_only=True)
    assert out.get("summary") == ""
    assert out.get("source") == "none"

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
