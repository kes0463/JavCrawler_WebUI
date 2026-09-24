"""Insight analytics aggregation for WebAPI and Qt InsightModel."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

PHASE_CORE = "core"
PHASE_TRENDS = "trends"
PHASE_RECOMMEND = "recommend"
PHASE_COLLECTION = "collection"

ALL_PHASES = (PHASE_CORE, PHASE_TRENDS, PHASE_RECOMMEND, PHASE_COLLECTION)


def _excluded_genres() -> set[str]:
    from javstory.config.app_config import similarity_excluded_genres_from_env

    return similarity_excluded_genres_from_env()


_RECOMMEND_TTL_SEC = 300.0
_OVERVIEW_TTL_SEC = 120.0


def _safe_call(fn: Callable[[], Any], default: Any, *, label: str = "") -> Any:
    try:
        return fn()
    except Exception:
        import traceback

        tag = f"[{label}] " if label else ""
        print(f"[Insight] {tag}데이터 조회 실패: {traceback.format_exc()}", flush=True)
        return default


class InsightService:
    def __init__(self) -> None:
        self._recommend_cache: tuple[float, dict[str, Any]] | None = None
        self._overview_cache: tuple[float, dict[str, Any]] | None = None

    def fetch_phase(self, phase: str, *, force_refresh: bool = False) -> dict[str, Any]:
        excluded = _excluded_genres()
        if phase == PHASE_CORE:
            return self.fetch_overview(force_refresh=force_refresh)
        if phase == PHASE_TRENDS:
            return self._fetch_trends(excluded)
        if phase == PHASE_RECOMMEND:
            return self.fetch_recommend(force_refresh=force_refresh)
        if phase == PHASE_COLLECTION:
            return self._fetch_collection(force_refresh=force_refresh)
        return {}

    def fetch_overview(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force_refresh and self._overview_cache is not None:
            cached_at, data = self._overview_cache
            if now - cached_at < _OVERVIEW_TTL_SEC:
                return data
        data = self._fetch_core(_excluded_genres(), force_refresh=force_refresh)
        if not force_refresh:
            self._overview_cache = (now, data)
        return data

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
        self._overview_cache = None

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

        empty_distribution = {"actors": [], "genres": [], "makers": []}
        empty_digest = {
            "has_data": False,
            "lines": [],
            "empty_message": "이번 주 시청 이력이 없습니다.",
        }

        tasks = {
            "stats": lambda: _safe_call(get_library_stats, {}, label="stats"),
            "top_actors": lambda: _safe_call(lambda: get_top_actors(5), [], label="top_actors"),
            "top_genres": lambda: _safe_call(
                lambda: get_top_genres(8, excluded=excluded), [], label="top_genres"
            ),
            "top_makers": lambda: _safe_call(lambda: get_top_makers(5), [], label="top_makers"),
            "recent_trend": lambda: _safe_call(
                lambda: compute_recent_trend(excluded_genres=excluded),
                {},
                label="recent_trend",
            ),
            "pipeline": lambda: _safe_call(lambda: get_pipeline_report(30), {}, label="pipeline"),
            "monthly_genre_trend": lambda: _safe_call(
                lambda: get_monthly_genre_trend(3), [], label="monthly_genre_trend"
            ),
            "monthly_additions": lambda: _safe_call(
                lambda: get_monthly_library_additions(6), [], label="monthly_additions"
            ),
            "weekly_digest": lambda: _safe_call(
                lambda: get_weekly_digest(force_refresh=force_refresh, excluded=excluded),
                empty_digest,
                label="weekly_digest",
            ),
            "distribution": lambda: _safe_call(
                lambda: get_library_distribution(force_refresh=force_refresh),
                empty_distribution,
                label="distribution",
            ),
        }

        result: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                result[futures[future]] = future.result()
        return result

    @staticmethod
    def _fetch_trends(excluded: set[str]) -> dict[str, Any]:
        from javstory.analytics.library_stats import compute_taste_profile, get_monthly_genre_trend
        from javstory.analytics.preference_engine import compute_recent_trend

        profile = _safe_call(compute_taste_profile, {}, label="taste_profile")
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
            "monthly_genre_trend": _safe_call(
                lambda: get_monthly_genre_trend(6), [], label="monthly_genre_trend"
            ),
            "recent_trend": _safe_call(
                lambda: compute_recent_trend(excluded_genres=excluded),
                {},
                label="recent_trend",
            ),
        }

    @staticmethod
    def _fetch_recommend() -> dict[str, Any]:
        from javstory.analytics.actor_content_recommender import recommend_favorite_actor_content
        from javstory.analytics.library_stats import get_today_recommendation, get_unwatched_gems
        from javstory.analytics.preference_engine import get_recommendations

        tasks = {
            "today_recs": lambda: _safe_call(
                lambda: get_today_recommendation(12), [], label="today_recs"
            ),
            "next_watch": lambda: _safe_call(
                lambda: get_recommendations(12, use_embeddings=False),
                [],
                label="next_watch",
            ),
            "hidden_gems": lambda: _safe_call(
                lambda: get_unwatched_gems(12), [], label="hidden_gems"
            ),
            "favorite_actor_picks": lambda: _safe_call(
                lambda: recommend_favorite_actor_content(12),
                [],
                label="favorite_actor_picks",
            ),
        }
        result: dict[str, Any] = {key: [] for key in tasks}
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                result[key] = future.result()
        return result

    @staticmethod
    def _fetch_collection(*, force_refresh: bool = False) -> dict[str, Any]:
        from javstory.analytics.library_stats import get_actor_collection_stats, get_library_distribution
        from javstory.analytics.pipeline_stats import get_pipeline_report

        empty_distribution = {"actors": [], "genres": [], "makers": []}
        tasks = {
            "distribution": lambda: _safe_call(
                lambda: get_library_distribution(force_refresh=force_refresh),
                empty_distribution,
                label="distribution",
            ),
            "actor_collections": lambda: _safe_call(
                lambda: get_actor_collection_stats(12), {}, label="actor_collections"
            ),
            "pipeline": lambda: _safe_call(lambda: get_pipeline_report(30), {}, label="pipeline"),
        }
        result: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                result[futures[future]] = future.result()
        return result
