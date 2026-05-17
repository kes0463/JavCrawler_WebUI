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
