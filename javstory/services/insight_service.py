"""Insight analytics aggregation for WebAPI and Qt InsightModel."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

PHASE_CORE = "core"
PHASE_TRENDS = "trends"
PHASE_RECOMMEND = "recommend"
PHASE_COLLECTION = "collection"

ALL_PHASES = (PHASE_CORE, PHASE_TRENDS, PHASE_RECOMMEND, PHASE_COLLECTION)


def _excluded_genres() -> set[str]:
    from javstory.config.app_config import similarity_excluded_genres_from_env

    return similarity_excluded_genres_from_env()


_RECOMMEND_TTL_SEC = 300.0


class InsightService:
    def __init__(self) -> None:
        self._recommend_cache: tuple[float, dict[str, Any]] | None = None

    def fetch_phase(self, phase: str, *, force_refresh: bool = False) -> dict[str, Any]:
        excluded = _excluded_genres()
        if phase == PHASE_CORE:
            return self._fetch_core(excluded, force_refresh=force_refresh)
        if phase == PHASE_TRENDS:
            return self._fetch_trends(excluded)
        if phase == PHASE_RECOMMEND:
            return self.fetch_recommend(force_refresh=force_refresh)
        if phase == PHASE_COLLECTION:
            return self._fetch_collection(force_refresh=force_refresh)
        return {}

    def fetch_overview(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return self._fetch_core(_excluded_genres(), force_refresh=force_refresh)

    def fetch_trends(self) -> dict[str, Any]:
        return self._fetch_trends(_excluded_genres())

    def fetch_recommend(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force_refresh and self._recommend_cache is not None:
            cached_at, data = self._recommend_cache
            if now - cached_at < _RECOMMEND_TTL_SEC:
                return data
        data = self._fetch_recommend()
        self._recommend_cache = (now, data)
        return data

    def invalidate_recommend_cache(self) -> None:
        self._recommend_cache = None

    def fetch_collection(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return self._fetch_collection(force_refresh=force_refresh)

    @staticmethod
    def _fetch_core(excluded: set[str], *, force_refresh: bool = False) -> dict[str, Any]:
        from javstory.analytics.library_stats import (
            get_library_distribution,
            get_library_stats,
            get_monthly_genre_trend,
            get_monthly_library_additions,
        )
        from javstory.analytics.pipeline_stats import get_pipeline_report
        from javstory.analytics.preference_engine import (
            compute_recent_trend,
            get_top_actors,
            get_top_genres,
            get_top_makers,
        )
        from javstory.analytics.weekly_digest import get_weekly_digest

        def _safe(fn, default):
            try:
                return fn()
            except Exception:
                return default

        distribution = _safe(
            lambda: get_library_distribution(force_refresh=force_refresh),
            {"actors": [], "genres": [], "makers": []},
        )
        return {
            "stats": _safe(get_library_stats, {}),
            "top_actors": _safe(lambda: get_top_actors(5), []),
            "top_genres": _safe(lambda: get_top_genres(8, excluded=excluded), []),
            "top_makers": _safe(lambda: get_top_makers(5), []),
            "recent_trend": _safe(lambda: compute_recent_trend(excluded_genres=excluded), {}),
            "pipeline": _safe(lambda: get_pipeline_report(30), {}),
            "monthly_genre_trend": _safe(lambda: get_monthly_genre_trend(3), []),
            "monthly_additions": _safe(lambda: get_monthly_library_additions(6), []),
            "weekly_digest": _safe(
                lambda: get_weekly_digest(force_refresh=force_refresh, excluded=excluded),
                {"has_data": False, "lines": [], "empty_message": "이번 주 시청 이력이 없습니다."},
            ),
            "distribution": distribution,
        }

    @staticmethod
    def _fetch_trends(excluded: set[str]) -> dict[str, Any]:
        from javstory.analytics.library_stats import compute_taste_profile, get_monthly_genre_trend
        from javstory.analytics.preference_engine import compute_recent_trend

        def _safe(fn, default):
            try:
                return fn()
            except Exception:
                return default

        profile = _safe(compute_taste_profile, {})
        return {
            "watch_summary": {
                "watched_count": int(profile.get("watched_count") or 0),
                "has_data": bool(profile.get("has_data")),
                "top_genres": profile.get("top_genres") or [],
                "top_actors": profile.get("top_actors") or [],
                "scene_tags": profile.get("scene_tags") or [],
                "empty_message": profile.get("empty_message")
                or "아직 시청 이력이 없습니다. 재생·별점 후 다시 확인하세요.",
            },
            "monthly_genre_trend": _safe(lambda: get_monthly_genre_trend(6), []),
            "recent_trend": _safe(lambda: compute_recent_trend(excluded_genres=excluded), {}),
        }

    @staticmethod
    def _fetch_recommend() -> dict[str, Any]:
        from javstory.analytics.actor_content_recommender import recommend_favorite_actor_content
        from javstory.analytics.library_stats import get_today_recommendation, get_unwatched_gems
        from javstory.analytics.preference_engine import get_recommendations

        def _safe(fn, default):
            try:
                return fn()
            except Exception:
                return default

        tasks = {
            "today_recs": lambda: _safe(lambda: get_today_recommendation(12), []),
            "next_watch": lambda: _safe(lambda: get_recommendations(12, use_embeddings=False), []),
            "hidden_gems": lambda: _safe(lambda: get_unwatched_gems(12), []),
            "favorite_actor_picks": lambda: _safe(lambda: recommend_favorite_actor_content(12), []),
        }
        result: dict[str, Any] = {key: [] for key in tasks}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                result[key] = future.result()
        return result

    @staticmethod
    def _fetch_collection(*, force_refresh: bool = False) -> dict[str, Any]:
        from javstory.analytics.library_stats import get_actor_collection_stats, get_library_distribution
        from javstory.analytics.pipeline_stats import get_pipeline_report

        return {
            "distribution": get_library_distribution(force_refresh=force_refresh),
            "actor_collections": get_actor_collection_stats(12),
            "pipeline": get_pipeline_report(30),
        }
