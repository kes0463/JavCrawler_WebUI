"""InsightService unit tests."""

from __future__ import annotations

import pytest

from javstory.services.insight_service import (
    PHASE_COLLECTION,
    PHASE_CORE,
    PHASE_RECOMMEND,
    PHASE_TRENDS,
    InsightService,
)


@pytest.fixture
def svc() -> InsightService:
    return InsightService()


def test_fetch_core_keys(svc: InsightService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.insight_service.InsightService._fetch_core",
        lambda *a, **k: {
            "stats": {"total": 1},
            "top_actors": [],
            "top_genres": [],
            "top_makers": [],
            "recent_trend": {},
            "weekly_digest": {},
            "pipeline": {},
            "monthly_genre_trend": [],
            "monthly_additions": [],
            "distribution": {},
            "persona": {},
        },
    )
    data = svc.fetch_phase(PHASE_CORE)
    assert "stats" in data
    assert data["stats"]["total"] == 1


def test_fetch_trends_keys(svc: InsightService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.insight_service.InsightService._fetch_trends",
        lambda *a, **k: {
            "watch_summary": {"has_data": False, "watched_count": 0, "top_genres": [], "top_actors": []},
            "monthly_genre_trend": [],
            "recent_trend": {},
        },
    )
    data = svc.fetch_trends()
    assert "watch_summary" in data
    assert "monthly_genre_trend" in data


def test_fetch_recommend_keys(svc: InsightService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.insight_service.InsightService._fetch_recommend",
        lambda *a, **k: {
            "today_recs": [],
            "next_watch": [],
            "hidden_gems": [],
            "favorite_actor_picks": [],
        },
    )
    data = svc.fetch_recommend()
    assert "next_watch" in data
    cached = svc.fetch_recommend()
    assert cached is data or cached == data


def test_fetch_recommend_force_refresh(svc: InsightService, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _fake(*_a, **_k):
        calls["n"] += 1
        return {
            "today_recs": [],
            "next_watch": [],
            "hidden_gems": [],
            "favorite_actor_picks": [],
        }

    monkeypatch.setattr(
        "javstory.services.insight_service.InsightService._fetch_recommend",
        _fake,
    )
    svc.fetch_recommend()
    svc.fetch_recommend()
    assert calls["n"] == 1
    svc.fetch_recommend(force_refresh=True)
    assert calls["n"] == 2
    svc.invalidate_recommend_cache()
    svc.fetch_recommend()
    assert calls["n"] == 3


def test_fetch_collection_keys(svc: InsightService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.insight_service.InsightService._fetch_collection",
        lambda *a, **k: {
            "distribution": {"actors": [], "genres": [], "makers": []},
            "actor_collections": {"has_data": False, "actors": []},
            "pipeline": {"days": 30},
        },
    )
    data = svc.fetch_collection()
    assert "actor_collections" in data


def test_unknown_phase_returns_empty(svc: InsightService) -> None:
    assert svc.fetch_phase("unknown") == {}


def test_get_monthly_library_additions_shape() -> None:
    from javstory.analytics.library_stats import get_monthly_library_additions

    rows = get_monthly_library_additions(3)
    assert len(rows) == 3
    for row in rows:
        assert "month" in row
        assert "label" in row
        assert "count" in row
        assert isinstance(row["count"], int)
