"""Insight 확장 — harvest 알림, taste vector, 추천."""

from __future__ import annotations

import os

import pytest


def test_insight_harvest_alert_threshold(monkeypatch):
    from javstory.analytics.harvest_alert import (
        evaluate_harvest_taste_alert,
        insight_harvest_alert_threshold,
    )

    monkeypatch.setenv("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", "1")
    monkeypatch.setenv("JAVSTORY_INSIGHT_HARVEST_ALERT_THRESHOLD", "0.85")
    assert insight_harvest_alert_threshold() == 0.85

    monkeypatch.setenv("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", "0")
    assert evaluate_harvest_taste_alert("ANY-001") is None


def test_compute_taste_profile_shape():
    from javstory.analytics.library_stats import compute_taste_profile, compute_taste_vector

    data = compute_taste_profile()
    assert "watched_count" in data
    assert "has_data" in data
    assert "top_genres" in data
    assert "top_actors" in data
    assert "scene_tags" in data

    legacy = compute_taste_vector()
    assert "axes" in legacy
    if data.get("has_data"):
        assert len(data["axes"]) == 4
        for ax in data["axes"]:
            assert "label" in ax
            assert "value" in ax
            assert "hint" in ax
            assert "pct" in ax
            assert 0.0 <= float(ax["value"]) <= 1.0


def test_get_recommendations_fallback(monkeypatch):
    from javstory.analytics.preference_engine import get_recommendations

    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "0")
    recs = get_recommendations(3)
    assert isinstance(recs, list)
    for row in recs:
        assert row.get("source") == "rules"
        assert "product_code" in row


def test_get_watch_heatmap():
    from javstory.analytics.library_stats import get_watch_heatmap

    data = get_watch_heatmap(2026)
    assert data["year"] == 2026
    assert isinstance(data["days"], dict)


def test_pipeline_report():
    from javstory.analytics.pipeline_stats import get_pipeline_report

    report = get_pipeline_report(7)
    assert "total_events" in report
    assert "days" in report


def test_get_unwatched_gems_shape():
    from javstory.analytics.library_stats import get_unwatched_gems

    gems = get_unwatched_gems(5)
    assert isinstance(gems, list)
    for row in gems:
        assert row.get("gem_type") in ("unwatched", "underrated")
        assert "product_code" in row
        assert "reason" in row
        assert "rec_score" in row
        assert 0.0 <= float(row["rec_score"]) <= 1.0


def test_get_preference_timeline_shape():
    from javstory.analytics.library_stats import get_preference_timeline, get_monthly_genre_trend

    tl = get_preference_timeline("month", 6)
    assert "has_data" in tl
    assert "series" in tl
    assert "legend" in tl
    assert "drift_note" in tl
    assert tl["granularity"] == "month"
    if tl.get("has_data"):
        assert len(tl["series"]) >= 1
        row = tl["series"][0]
        assert "period" in row
        assert "stacks" in row
        pct_sum = sum(s["pct"] for s in row["stacks"])
        assert 95 <= pct_sum <= 105

    monthly = get_monthly_genre_trend(3)
    assert isinstance(monthly, list)


def test_get_weekly_digest_shape():
    from javstory.analytics.weekly_digest import get_weekly_digest, generate_weekly_digest

    data = get_weekly_digest(force_refresh=True)
    assert "has_data" in data
    assert "week_label" in data
    assert "lines" in data
    assert isinstance(data["lines"], list)
    assert "generated_at" in data

    regen = generate_weekly_digest()
    assert regen.get("period_key")


def test_get_actor_collection_stats_shape():
    from javstory.analytics.library_stats import get_actor_collection_stats

    data = get_actor_collection_stats(8)
    assert "has_data" in data
    assert "actors" in data
    assert isinstance(data["actors"], list)
    for row in data["actors"]:
        assert "name" in row
        assert "total" in row
        assert "completed" in row
        assert "completion_rate" in row
        assert row["completed"] <= row["total"]
        assert 0.0 <= float(row["completion_rate"]) <= 1.0


def test_get_unwatched_gems_respects_min_score(monkeypatch):
    from javstory.analytics.library_stats import get_unwatched_gems

    monkeypatch.setenv("JAVSTORY_HIDDEN_GEMS_MIN_SCORE", "0.99")
    gems = get_unwatched_gems(10, min_score=0.99)
    assert isinstance(gems, list)
    for row in gems:
        assert float(row["rec_score"]) >= 0.99
