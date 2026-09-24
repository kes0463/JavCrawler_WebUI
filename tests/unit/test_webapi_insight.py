"""webapi insight route tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def insight_client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from webapi.routes import insight as insight_mod

    class FakeInsight:
        def fetch_overview(self, *, force_refresh=False):
            return {
                "stats": {"total": 10, "avg_rating": 4.0, "watched_count": 5, "completed": 2, "completion_rate": 0.4, "rated_count": 3, "total_watch_hours": 12.0},
                "top_actors": [{"name": "A", "score": 10}],
                "top_genres": [{"name": "G", "score": 8}],
                "top_makers": [{"name": "M", "score": 5}],
                "recent_trend": {"actors": [], "genres": []},
                "weekly_digest": {"has_data": False, "lines": []},
                "pipeline": {"days": 30, "total_events": 0},
                "monthly_genre_trend": [],
                "monthly_additions": [{"month": "2026-06", "label": "6월", "count": 1}],
                "distribution": {"actors": [], "genres": [], "makers": []},
            }

        def fetch_trends(self):
            return {
                "watch_summary": {"has_data": True, "watched_count": 10, "top_genres": [], "top_actors": []},
                "monthly_genre_trend": [{"month": "2026-06", "genres": [{"name": "G", "count": 3}]}],
                "recent_trend": {},
            }

        def fetch_recommend(self, *, force_refresh=False):
            return {
                "today_recs": [],
                "next_watch": [{"product_code": "TST-001", "title_ko": "t", "rec_score": 0.9}],
                "hidden_gems": [],
                "favorite_actor_picks": [],
            }

        def invalidate_recommend_cache(self):
            pass

        def fetch_collection(self, *, force_refresh=False):
            return {
                "distribution": {"actors": [], "genres": [], "makers": []},
                "actor_collections": {"has_data": False, "actors": []},
                "pipeline": {"days": 30},
            }

        def fetch_phase(self, phase, *, force_refresh=False):
            if phase == "core":
                return self.fetch_overview(force_refresh=force_refresh)
            if phase == "trends":
                return self.fetch_trends()
            if phase == "recommend":
                return self.fetch_recommend(force_refresh=force_refresh)
            if phase == "collection":
                return self.fetch_collection(force_refresh=force_refresh)
            return {}

    monkeypatch.setattr(insight_mod, "_insight", FakeInsight())
    insight_mod._refresh_running = False

    app = FastAPI()
    app.include_router(insight_mod.router, prefix="/api/insight")
    return TestClient(app)


def test_insight_overview(insight_client) -> None:
    res = insight_client.get("/api/insight/overview")
    assert res.status_code == 200
    body = res.json()
    assert body["stats"]["total"] == 10
    assert len(body["top_actors"]) == 1


def test_insight_trends(insight_client) -> None:
    res = insight_client.get("/api/insight/trends")
    assert res.status_code == 200
    body = res.json()
    assert body["watch_summary"]["watched_count"] == 10
    assert len(body["monthly_genre_trend"]) == 1


def test_insight_recommend(insight_client) -> None:
    res = insight_client.get("/api/insight/recommend")
    assert res.status_code == 200
    assert res.json()["next_watch"][0]["product_code"] == "TST-001"


def test_insight_collection(insight_client) -> None:
    res = insight_client.get("/api/insight/collection")
    assert res.status_code == 200
    assert "distribution" in res.json()


def test_insight_refresh_starts_background_job(insight_client) -> None:
    """POST /refresh no longer blocks — it kicks off a background job with WS progress."""
    res = insight_client.post("/api/insight/refresh")
    assert res.status_code == 200
    assert res.json() == {"started": True}


def test_insight_refresh_rejects_when_already_running(insight_client) -> None:
    from webapi.routes import insight as insight_mod

    insight_mod._refresh_running = True
    try:
        res = insight_client.post("/api/insight/refresh")
        assert res.status_code == 200
        assert res.json() == {"started": False, "already_running": True}
    finally:
        insight_mod._refresh_running = False


def test_run_refresh_job_broadcasts_progress_and_keeps_llamacpp_warm(monkeypatch) -> None:
    import asyncio

    from webapi.routes import insight as insight_mod

    class FakeInsight:
        def __init__(self):
            self.calls: list[str] = []

        def invalidate_recommend_cache(self):
            pass

        def fetch_phase(self, phase, *, force_refresh=False):
            self.calls.append(phase)
            return {}

    fake_insight = FakeInsight()
    monkeypatch.setattr(insight_mod, "_insight", fake_insight)

    events: list[dict] = []

    async def _fake_broadcast(event):
        events.append(event)

    monkeypatch.setattr(insight_mod, "_broadcast", _fake_broadcast)

    monkeypatch.setattr(
        "javstory.analytics.persona_card.get_persona_card",
        lambda **kw: fake_insight.calls.append("persona_card") or {},
    )

    insight_mod._refresh_running = True
    asyncio.run(insight_mod._run_refresh_job())

    assert fake_insight.calls == ["core", "persona_card", "trends", "recommend", "collection"]
    assert insight_mod._refresh_running is False
    assert events[-1]["type"] == "refresh_complete"
