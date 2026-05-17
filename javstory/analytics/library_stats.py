"""
라이브러리 통계 및 오늘의 추천

- get_library_stats(): 전체 라이브러리 요약 통계
- get_today_recommendation(limit): 취향 점수 최고 미시청 작품 목록
"""
from __future__ import annotations

import datetime
from collections import Counter
from typing import List, Dict, Any

from javstory.harvest.database import get_db_session_ctx, JAVMetadata, WatchHistory
from javstory.analytics.preference_engine import get_recommendation_score


def get_library_stats() -> Dict[str, Any]:
    """
    라이브러리 전체 통계를 반환합니다.
    Returns:
        {
            "total": int,              # 전체 작품 수
            "completed": int,          # 완독 작품 수
            "completion_rate": float,  # 완독률 (0.0~1.0)
            "avg_rating": float,       # 평균 별점
            "rated_count": int,        # 별점 부여 작품 수
            "watched_count": int,      # 시청 이력 있는 작품 수
            "total_watch_hours": float, # 총 시청 시간(시간)
        }
    """
    with get_db_session_ctx() as session:
        total = session.query(JAVMetadata).count()
        histories = session.query(WatchHistory).all()

        watched_count = len(histories)
        completed = sum(1 for h in histories if h.is_completed)
        total_watch_sec = sum(h.watch_duration or 0 for h in histories)
        rated = [h.rating for h in histories if h.rating and h.rating > 0]
        avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0

        return {
            "total": total,
            "completed": completed,
            "completion_rate": round(completed / watched_count, 4) if watched_count > 0 else 0.0,
            "avg_rating": avg_rating,
            "rated_count": len(rated),
            "watched_count": watched_count,
            "total_watch_hours": round(total_watch_sec / 3600, 1),
        }


def get_today_recommendation(limit: int = 6) -> List[Dict[str, Any]]:
    """
    사용자 취향 점수 기준 미시청 작품을 추천합니다.
    이미 시청한 작품(watch_history 존재)은 제외합니다.
    Returns:
        [{"product_code", "title_ko", "cover_path", "actors_ko", "rec_score"}, ...]
    """
    with get_db_session_ctx() as session:
        # 시청 이력이 있는 품번 집합
        watched_codes = {
            r.product_code
            for r in session.query(WatchHistory.product_code).all()
        }

        # 미시청 + 커버이미지 있는 + KO 제목 있는 작품 중 최신 200개만 후보
        candidates = (
            session.query(JAVMetadata)
            .filter(
                ~JAVMetadata.product_code.in_(watched_codes),
                JAVMetadata.cover_image_local_path.isnot(None),
                JAVMetadata.title_ko.isnot(None),
            )
            .order_by(JAVMetadata.updated_at.desc())
            .limit(200)
            .all()
        )

    # 취향 점수 계산 (DB 세션 외부에서 실행)
    scored: List[Dict[str, Any]] = []
    for row in candidates:
        rec = get_recommendation_score(row.product_code)
        scored.append({
            "product_code": row.product_code,
            "title_ko": row.title_ko or "",
            "cover_path": row.cover_image_local_path or "",
            "actors_ko": row.actors_ko or "",
            "release_date": row.release_date or "",
            "rec_score": rec,
        })

    # 점수 내림차순 정렬
    scored.sort(key=lambda x: x["rec_score"], reverse=True)
    return scored[:limit]


def get_monthly_genre_trend(months: int = 3) -> List[Dict[str, Any]]:
    """
    최근 N개월 시청 패턴에서 월별 장르 선호 변화를 반환합니다.
    Returns: [{"month": "2026-04", "genres": [{"name", "count"}, ...]}, ...]
    """
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30 * months)

    with get_db_session_ctx() as session:
        histories = (
            session.query(WatchHistory)
            .filter(WatchHistory.updated_at >= cutoff)
            .order_by(WatchHistory.updated_at.desc())
            .all()
        )

        if not histories:
            return []

        # 월별 집계
        monthly: Dict[str, Dict[str, int]] = {}
        for h in histories:
            month_key = h.updated_at.strftime("%Y-%m") if h.updated_at else "unknown"
            if month_key == "unknown":
                continue
            if month_key not in monthly:
                monthly[month_key] = {}

            row = session.query(JAVMetadata).filter_by(product_code=h.product_code).first()
            if not row:
                continue
            genres_raw = row.genres_ko or row.genres or ""
            for g in [v.strip() for v in genres_raw.replace("、", ",").split(",") if v.strip()]:
                monthly[month_key][g] = monthly[month_key].get(g, 0) + 1

    result = []
    for month_key in sorted(monthly.keys(), reverse=True):
        genre_counts = sorted(monthly[month_key].items(), key=lambda x: x[1], reverse=True)[:5]
        result.append({
            "month": month_key,
            "genres": [{"name": g, "count": c} for g, c in genre_counts],
        })
    return result


def get_library_distribution() -> Dict[str, List[Dict[str, Any]]]:
    """
    라이브러리 전체에서 배우/장르/제작사별 보유 작품 수를 집계합니다.
    - 설정된 '제외 장르'는 집계에서 제외합니다.
    Returns:
        {
            "actors": [{"name": str, "count": int}, ...],
            "genres": [{"name": str, "count": int}, ...],
            "makers": [{"name": str, "count": int}, ...]
        }
    """
    import os
    from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES
    
    # 제외 장르 로드
    excluded_str = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
    if excluded_str:
        excluded = {v.strip() for v in excluded_str.split(",") if v.strip()}
    else:
        excluded = set(SIMILARITY_EXCLUDED_GENRES)

    with get_db_session_ctx() as session:
        # 모든 메타데이터 로드
        rows = session.query(
            JAVMetadata.actors_ko, JAVMetadata.actors,
            JAVMetadata.genres_ko, JAVMetadata.genres,
            JAVMetadata.maker_ko, JAVMetadata.maker
        ).all()

        actor_counter = Counter()
        genre_counter = Counter()
        maker_counter = Counter()

        for r in rows:
            # 배우 파싱
            actors_raw = r.actors_ko or r.actors or ""
            for a in [v.strip() for v in actors_raw.replace("、", ",").split(",") if v.strip()]:
                actor_counter[a] += 1

            # 장르 파싱
            genres_raw = r.genres_ko or r.genres or ""
            for g in [v.strip() for v in genres_raw.replace("、", ",").split(",") if v.strip()]:
                if g not in excluded:
                    genre_counter[g] += 1

            # 제작사
            m = (r.maker_ko or r.maker or "").strip()
            if m:
                maker_counter[m] += 1

        return {
            "actors": [{"name": k, "count": v} for k, v in actor_counter.most_common(30)],
            "genres": [{"name": k, "count": v} for k, v in genre_counter.most_common(30)],
            "makers": [{"name": k, "count": v} for k, v in maker_counter.most_common(30)],
        }


def _parse_comma_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


def _hhi_normalized(counts: list[int]) -> float:
    """Herfindahl 지수 → 0(분산)~1(편중) 정규화."""
    if not counts:
        return 0.0
    total = sum(counts)
    if total <= 0:
        return 0.0
    shares = [c / total for c in counts if c > 0]
    if len(shares) <= 1:
        return 1.0 if len(shares) == 1 else 0.0
    hhi = sum(s * s for s in shares)
    n = len(shares)
    return round((hhi - 1.0 / n) / (1.0 - 1.0 / n), 4)


def _parse_release_year(release_date: str | None) -> int | None:
    if not release_date:
        return None
    s = str(release_date).strip()
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


def _counter_top(counter: Counter, n: int = 3) -> List[Dict[str, Any]]:
    total = sum(counter.values()) or 1
    out: List[Dict[str, Any]] = []
    for name, count in counter.most_common(n):
        out.append({
            "name": name,
            "count": int(count),
            "share_pct": int(round(100 * count / total)),
        })
    return out


def _sample_scene_tags_from_watched(max_products: int = 5) -> List[Dict[str, Any]]:
    """최근 시청 작품 Grok 캐시에서 씬 태그만 가볍게 집계."""
    tag_counter: Counter = Counter()
    codes: List[str] = []
    with get_db_session_ctx() as session:
        rows = (
            session.query(WatchHistory)
            .order_by(WatchHistory.updated_at.desc())
            .limit(max_products * 2)
            .all()
        )
        seen: set[str] = set()
        for h in rows:
            pc = str(h.product_code or "").strip().upper()
            if pc and pc not in seen:
                seen.add(pc)
                codes.append(pc)
            if len(codes) >= max_products:
                break

    try:
        from javstory.translation.story_grok_module import load_cached_grok_json_flexible
    except ImportError:
        return []

    for pc in codes:
        grok = load_cached_grok_json_flexible(pc)
        if not grok or grok.get("code_mismatch") or grok.get("verification_ok") is False:
            continue
        for s in grok.get("scenes") or []:
            if not isinstance(s, dict):
                continue
            for t in s.get("key_tags") or []:
                if isinstance(t, str) and t.strip():
                    tag_counter[t.strip()] += 1

    return [{"name": k, "count": v} for k, v in tag_counter.most_common(8)]


def compute_taste_profile() -> Dict[str, Any]:
    """
    시청 이력 중심 취향 프로필 (읽기 쉬운 축 + TOP 목록).
    Returns:
        watched_count, has_data, axes[{label, value, pct, hint}], top_genres, top_actors, scene_tags
    """
    import os
    from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES

    excluded_str = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
    excluded = (
        {v.strip() for v in excluded_str.split(",") if v.strip()}
        if excluded_str
        else set(SIMILARITY_EXCLUDED_GENRES)
    )

    current_year = datetime.datetime.now().year
    watched_genres: Counter = Counter()
    watched_actors: Counter = Counter()
    recent_year_hits = 0
    watched_with_year = 0
    watched_n = 0
    completed = 0

    with get_db_session_ctx() as session:
        histories = session.query(WatchHistory).all()
        completed = sum(1 for h in histories if h.is_completed)
        watched_n = len(histories)
        meta_by_code = {
            str(r.product_code or "").strip().upper(): r
            for r in session.query(JAVMetadata).filter(
                JAVMetadata.product_code.in_(
                    [str(h.product_code or "").strip().upper() for h in histories if h.product_code]
                )
            ).all()
            if r.product_code
        }

        for h in histories:
            pc = str(h.product_code or "").strip().upper()
            row = meta_by_code.get(pc)
            if not row:
                continue
            for g in _parse_comma_list(row.genres_ko or row.genres):
                if g not in excluded:
                    watched_genres[g] += 1
            for a in _parse_comma_list(row.actors_ko or row.actors_ja or row.actors):
                watched_actors[a] += 1
            yr = _parse_release_year(row.release_date)
            if yr:
                watched_with_year += 1
                if yr >= current_year - 3:
                    recent_year_hits += 1

    top_genres = _counter_top(watched_genres, 5)
    top_actors = _counter_top(watched_actors, 5)
    scene_tags = _sample_scene_tags_from_watched(5) if watched_n > 0 else []

    if watched_n <= 0:
        return {
            "watched_count": 0,
            "has_data": False,
            "axes": [],
            "top_genres": [],
            "top_actors": [],
            "scene_tags": [],
            "empty_message": "아직 시청 이력이 없습니다. 재생·별점·좋아요 후 다시 확인하세요.",
        }

    new_release_pref = round(recent_year_hits / watched_with_year, 4) if watched_with_year > 0 else 0.0
    completion_focus = round(completed / watched_n, 4)

    genre_focus = _hhi_normalized(list(watched_genres.values())) if watched_genres else 0.0
    top_g = top_genres[0]["name"] if top_genres else ""
    genre_hint = (
        f"주로 『{top_g}』 등 {top_genres[0]['share_pct']}% 집중"
        if top_genres and genre_focus >= 0.55
        else (f"가장 많이 본 장르: {top_g}" if top_g else "장르 데이터 부족")
    )

    actor_variety = 0.0
    if watched_actors:
        actor_variety = min(1.0, len(watched_actors) / max(1, watched_n * 1.5))
    top_a = top_actors[0]["name"] if top_actors else ""
    actor_hint = (
        f"다양한 배우 탐색 ({len(watched_actors)}명)"
        if actor_variety >= 0.6
        else (f"자주 보는 배우: {top_a}" if top_a else "배우 데이터 부족")
    )

    axes = [
        {
            "key": "new_release",
            "label": "신작 취향",
            "value": new_release_pref,
            "pct": int(round(new_release_pref * 100)),
            "hint": (
                f"시청 작품의 {int(round(new_release_pref * 100))}%가 최근 3년 내 발매"
                if watched_with_year > 0
                else "발매연도 정보 없음"
            ),
        },
        {
            "key": "completion",
            "label": "완독 성향",
            "value": completion_focus,
            "pct": int(round(completion_focus * 100)),
            "hint": f"{completed}편 완독 / 시청 이력 {watched_n}편",
        },
        {
            "key": "genre_focus",
            "label": "장르 집중도",
            "value": genre_focus,
            "pct": int(round(genre_focus * 100)),
            "hint": genre_hint,
        },
        {
            "key": "actor_variety",
            "label": "배우 탐색 폭",
            "value": round(actor_variety, 4),
            "pct": int(round(actor_variety * 100)),
            "hint": actor_hint,
        },
    ]

    return {
        "watched_count": watched_n,
        "has_data": True,
        "axes": axes,
        "top_genres": top_genres,
        "top_actors": top_actors,
        "scene_tags": scene_tags,
        "empty_message": "",
    }


def compute_taste_vector() -> Dict[str, Any]:
    """하위 호환 + InsightModel JSON. 시청 프로필 전체를 반환."""
    profile = compute_taste_profile()
    profile["axes"] = profile.get("axes") or []
    return profile


def get_watch_heatmap(year: int | None = None) -> Dict[str, Any]:
    """
    날짜별 시청 횟수 (watch_history.updated_at 기준).
    Returns: {"year": int, "days": {"2026-05-01": 2, ...}, "max": int}
    """
    y = int(year or datetime.datetime.now().year)
    start = datetime.datetime(y, 1, 1)
    end = datetime.datetime(y, 12, 31, 23, 59, 59)
    day_counts: Counter = Counter()

    with get_db_session_ctx() as session:
        rows = (
            session.query(WatchHistory)
            .filter(
                WatchHistory.updated_at >= start,
                WatchHistory.updated_at <= end,
            )
            .all()
        )
        for h in rows:
            if not h.updated_at:
                continue
            key = h.updated_at.strftime("%Y-%m-%d")
            day_counts[key] += 1

    days = {k: int(v) for k, v in sorted(day_counts.items())}
    mx = max(days.values()) if days else 0
    return {"year": y, "days": days, "max": mx}
