"""Harvest 수집 완료 시 취향 일치 신작 토스트 판별."""

from __future__ import annotations

import os

from javstory.analytics.preference_engine import get_recommendation_score


def insight_harvest_alert_enabled() -> bool:
    raw = (os.environ.get("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", "1") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def insight_harvest_alert_threshold() -> float:
    try:
        v = float(os.environ.get("JAVSTORY_INSIGHT_HARVEST_ALERT_THRESHOLD", "0.85") or "0.85")
    except ValueError:
        v = 0.85
    return max(0.5, min(1.0, v))


def evaluate_harvest_taste_alert(product_code: str) -> str | None:
    """
    임계값 초과 시 토스트 메시지 문자열을 반환, 아니면 None.
    """
    if not insight_harvest_alert_enabled():
        return None
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    score = get_recommendation_score(pc)
    threshold = insight_harvest_alert_threshold()
    if score < threshold:
        return None
    pct = int(round(score * 100))
    thr_pct = int(round(threshold * 100))
    return f"🔔 취향 일치 신작: {pc} — 일치도 {pct}% (기준 {thr_pct}%)"
