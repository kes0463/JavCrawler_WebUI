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

    monkeypatch.setattr(insight_mod, "_insight", FakeInsight())

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


def test_insight_refresh(insight_client) -> None:
    res = insight_client.post("/api/insight/refresh")
    assert res.status_code == 200
    assert res.json()["stats"]["total"] == 10
