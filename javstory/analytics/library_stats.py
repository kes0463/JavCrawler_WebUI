"""
라이브러리 통계 및 오늘의 추천

- get_library_stats(): 전체 라이브러리 요약 통계
- get_today_recommendation(limit): 취향 점수 최고 미시청 작품 목록
"""
from __future__ import annotations

import datetime
import time
from collections import Counter, defaultdict
from typing import List, Dict, Any

_DIST_CACHE: tuple[float, Dict[str, List[Dict[str, Any]]]] | None = None
_DIST_CACHE_TTL_SEC = 300.0

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


def _hidden_gems_env_float(key: str, default: float) -> float:
    import os
    try:
        v = float(os.environ.get(key, str(default)) or default)
    except ValueError:
        v = default
    return v


def _hidden_gems_env_int(key: str, default: int) -> int:
    import os
    try:
        v = int(os.environ.get(key, str(default)) or default)
    except ValueError:
        v = default
    return v


def _product_card_fields(row: JAVMetadata) -> Dict[str, str]:
    return {
        "product_code": row.product_code or "",
        "title_ko": row.title_ko or "",
        "cover_path": row.cover_image_local_path or "",
        "actors_ko": row.actors_ko or "",
        "release_date": row.release_date or "",
    }


def get_unwatched_gems(
    limit: int = 6,
    *,
    min_score: float | None = None,
    min_days: int | None = None,
) -> List[Dict[str, Any]]:
    """
    라이브러리 속 숨은 보석: 미감상·고취향 또는 저평가·고취향(괴리) 작품.

    Returns:
        [{
            product_code, title_ko, cover_path, actors_ko, release_date,
            rec_score, gem_type ('unwatched'|'underrated'), user_rating,
            days_in_library, gap_score, reason
        }, ...]
    """
    from javstory.harvest.database import UserPreference

    score_floor = min_score if min_score is not None else _hidden_gems_env_float(
        "JAVSTORY_HIDDEN_GEMS_MIN_SCORE", 0.55
    )
    score_floor = max(0.3, min(0.95, score_floor))
    days_floor = min_days if min_days is not None else _hidden_gems_env_int(
        "JAVSTORY_HIDDEN_GEMS_MIN_DAYS", 14
    )
    days_floor = max(0, days_floor)
    min_gap = _hidden_gems_env_float("JAVSTORY_HIDDEN_GEMS_MIN_GAP", 0.35)
    min_gap = max(0.1, min(0.9, min_gap))

    cap = max(1, min(20, int(limit or 6)))
    unwatched_cap = max(1, (cap * 2 + 2) // 3)
    underrated_cap = max(1, cap - unwatched_cap + 1)

    now = datetime.datetime.now()

    with get_db_session_ctx() as session:
        has_prefs = (
            session.query(UserPreference)
            .filter(UserPreference.time_slot == "all", UserPreference.score > 0)
            .limit(1)
            .first()
            is not None
        )
        if not has_prefs:
            return []

        watched_codes = {
            str(r.product_code or "").strip().upper()
            for r in session.query(WatchHistory.product_code).all()
            if r.product_code
        }

        unwatched_q = session.query(JAVMetadata).filter(
            JAVMetadata.cover_image_local_path.isnot(None),
            JAVMetadata.title_ko.isnot(None),
        )
        if watched_codes:
            unwatched_q = unwatched_q.filter(~JAVMetadata.product_code.in_(watched_codes))
        unwatched_rows = (
            unwatched_q.order_by(JAVMetadata.created_at.asc()).limit(400).all()
        )

        underrated_histories = (
            session.query(WatchHistory)
            .filter(
                (WatchHistory.disliked == True)  # noqa: E712
                | (
                    (WatchHistory.rating >= 1)
                    & (WatchHistory.rating <= 2)
                )
            )
            .all()
        )

        underrated_pcs = {
            str(h.product_code or "").strip().upper()
            for h in underrated_histories
            if h.product_code
        }
        meta_by_code: Dict[str, JAVMetadata] = {}
        if underrated_pcs:
            for row in session.query(JAVMetadata).filter(
                JAVMetadata.product_code.in_(list(underrated_pcs))
            ).all():
                pc = str(row.product_code or "").strip().upper()
                if pc:
                    meta_by_code[pc] = row

    unwatched_pool: List[Dict[str, Any]] = []
    for row in unwatched_rows:
        pc = str(row.product_code or "").strip().upper()
        if not pc:
            continue
        anchor = row.created_at or row.updated_at or now
        days = max(0, (now - anchor).days)
        if days < days_floor:
            continue
        rec = get_recommendation_score(pc)
        if rec < score_floor:
            continue
        unwatched_pool.append({
            **_product_card_fields(row),
            "rec_score": rec,
            "gem_type": "unwatched",
            "user_rating": 0,
            "days_in_library": days,
            "gap_score": rec,
            "reason": f"라이브러리에 {days}일째 · 미감상",
        })

    underrated_pool: List[Dict[str, Any]] = []
    for h in underrated_histories:
        pc = str(h.product_code or "").strip().upper()
        if not pc:
            continue
        row = meta_by_code.get(pc)
        if not row or not row.cover_image_local_path:
            continue
        rating = int(h.rating or 0)
        if h.disliked:
            rating_norm = 0.0
        else:
            rating_norm = max(0.0, min(1.0, rating / 5.0))
        rec = get_recommendation_score(pc)
        gap = round(rec - rating_norm, 4)
        if rec < score_floor or gap < min_gap:
            continue
        pct = int(round(rec * 100))
        if h.disliked:
            reason = f"싫어요 표시 · 취향 일치 {pct}%"
        else:
            reason = f"별점 {rating}점 · 취향 일치 {pct}%"
        anchor = row.created_at or row.updated_at or now
        days = max(0, (now - anchor).days)
        underrated_pool.append({
            **_product_card_fields(row),
            "rec_score": rec,
            "gem_type": "underrated",
            "user_rating": rating,
            "days_in_library": days,
            "gap_score": gap,
            "reason": reason,
        })

    unwatched_pool.sort(key=lambda x: (-x["rec_score"], -x["days_in_library"]))
    underrated_pool.sort(key=lambda x: (-x["gap_score"], -x["rec_score"]))

    seen: set[str] = set()
    out: List[Dict[str, Any]] = []

    def _take(pool: List[Dict[str, Any]], n: int) -> None:
        for item in pool:
            if len(out) >= cap:
                return
            pc = str(item.get("product_code") or "").strip().upper()
            if not pc or pc in seen:
                continue
            seen.add(pc)
            out.append(item)
            n -= 1
            if n <= 0:
                return

    _take(underrated_pool, underrated_cap)
    _take(unwatched_pool, unwatched_cap)
    if len(out) < cap:
        _take(underrated_pool, cap - len(out))
    if len(out) < cap:
        _take(unwatched_pool, cap - len(out))

    return out[:cap]


def _load_excluded_genres() -> set[str]:
    import os
    from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES

    excluded_str = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
    if excluded_str:
        return {v.strip() for v in excluded_str.split(",") if v.strip()}
    return set(SIMILARITY_EXCLUDED_GENRES)


def _period_key_from_date(dt: datetime.datetime, granularity: str) -> str | None:
    if not dt:
        return None
    gran = (granularity or "month").strip().lower()
    if gran == "quarter":
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
    return dt.strftime("%Y-%m")


def _period_label(period: str, granularity: str) -> str:
    gran = (granularity or "month").strip().lower()
    if gran == "quarter":
        return period.replace("-Q", " Q")
    parts = period.split("-")
    if len(parts) == 2:
        try:
            y, m = int(parts[0]), int(parts[1])
            return f"{y % 100:02d}.{m:02d}"
        except ValueError:
            pass
    return period


def _aggregate_genre_counts_by_period(
    months: int,
    granularity: str,
    excluded: set[str],
) -> Dict[str, Counter]:
    """시청 이력 → 기간별 장르 Counter."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30 * max(1, months))

    with get_db_session_ctx() as session:
        histories = (
            session.query(WatchHistory)
            .filter(WatchHistory.updated_at >= cutoff)
            .order_by(WatchHistory.updated_at.asc())
            .all()
        )
        if not histories:
            return {}

        pcs = list({
            str(h.product_code or "").strip().upper()
            for h in histories
            if h.product_code
        })
        meta_by_code: Dict[str, JAVMetadata] = {}
        if pcs:
            for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(pcs)).all():
                pc = str(row.product_code or "").strip().upper()
                if pc:
                    meta_by_code[pc] = row

    period_counts: Dict[str, Counter] = {}
    for h in histories:
        period = _period_key_from_date(h.updated_at, granularity)
        if not period:
            continue
        pc = str(h.product_code or "").strip().upper()
        row = meta_by_code.get(pc)
        if not row:
            continue
        counter = period_counts.setdefault(period, Counter())
        for g in _parse_comma_list(row.genres_ko or row.genres):
            if g not in excluded:
                counter[g] += 1

    return period_counts


def _compute_drift_note(series: List[Dict[str, Any]]) -> str:
    if len(series) < 2:
        return ""
    first = series[0]
    last = series[-1]
    first_top = next((s["name"] for s in first.get("stacks", []) if s.get("name") != "기타"), "")
    last_top = next((s["name"] for s in last.get("stacks", []) if s.get("name") != "기타"), "")
    if not first_top or not last_top:
        return ""
    if first_top == last_top:
        return f"최근 {len(series)}개 기간 동안 『{first_top}』 장르 비중이 가장 높습니다."
    return (
        f"{first.get('label', first.get('period', ''))}에는 『{first_top}』이 두드러졌고, "
        f"최근({last.get('label', last.get('period', ''))})에는 『{last_top}』 비중이 커졌습니다."
    )


def get_preference_timeline(
    granularity: str = "month",
    months: int = 6,
    *,
    top_genres: int = 5,
    excluded: set[str] | None = None,
) -> Dict[str, Any]:
    """
    분기/월별 장르 선호 스택 차트용 타임라인.
    Returns:
        has_data, granularity, legend[{name, color_index}], series[{period, label, total, stacks}],
        drift_note, empty_message
    """
    gran = (granularity or "month").strip().lower()
    if gran not in ("month", "quarter"):
        gran = "month"
    span = max(2, min(12, int(months or 6)))
    top_n = max(3, min(8, int(top_genres or 5)))
    excl = excluded if excluded is not None else _load_excluded_genres()

    period_counts = _aggregate_genre_counts_by_period(span, gran, excl)
    if not period_counts:
        return {
            "has_data": False,
            "granularity": gran,
            "months_span": span,
            "legend": [],
            "series": [],
            "drift_note": "",
            "empty_message": "최근 시청 이력이 없습니다. 재생 후 장르 변화를 확인하세요.",
        }

    periods = sorted(period_counts.keys())
    global_counter: Counter = Counter()
    for p in periods:
        global_counter.update(period_counts[p])
    top_names = [name for name, _ in global_counter.most_common(top_n)]

    legend = [{"name": n, "color_index": i} for i, n in enumerate(top_names)]
    if any(sum(period_counts[p].values()) > sum(period_counts[p].get(n, 0) for n in top_names) for p in periods):
        legend.append({"name": "기타", "color_index": -1})

    series: List[Dict[str, Any]] = []
    for period in periods:
        counter = period_counts[period]
        total = sum(counter.values())
        if total <= 0:
            continue
        stacks: List[Dict[str, Any]] = []
        used = 0
        for name in top_names:
            c = counter.get(name, 0)
            if c <= 0:
                continue
            pct = int(round(100 * c / total))
            stacks.append({"name": name, "count": c, "pct": pct})
            used += c
        other = total - used
        if other > 0:
            stacks.append({
                "name": "기타",
                "count": other,
                "pct": max(0, 100 - sum(s["pct"] for s in stacks)),
            })
        if stacks:
            drift_sum = sum(s["pct"] for s in stacks)
            if drift_sum != 100 and stacks:
                stacks[-1]["pct"] += 100 - drift_sum
        series.append({
            "period": period,
            "label": _period_label(period, gran),
            "total": total,
            "stacks": stacks,
        })

    return {
        "has_data": bool(series),
        "granularity": gran,
        "months_span": span,
        "legend": legend,
        "series": series,
        "drift_note": _compute_drift_note(series),
        "empty_message": "",
    }


def get_actor_collection_stats(
    limit: int = 12,
    *,
    min_works: int = 2,
) -> Dict[str, Any]:
    """
    배우별 라이브러리 보유·완독 현황.
    Returns:
        has_data, actors[{name, total, completed, watched, remaining, completion_rate, pct,
                          is_complete, hint, preference_score}], empty_message
    """
    import os
    from javstory.harvest.database import UserPreference

    cap = max(1, min(30, int(limit or 12)))
    min_total = max(2, min(20, int(min_works or 2)))
    try:
        env_min = int(os.environ.get("JAVSTORY_ACTOR_COLLECTION_MIN_WORKS", str(min_total)) or min_total)
        min_total = max(2, min(20, env_min))
    except ValueError:
        pass
    try:
        cap = max(1, min(30, int(os.environ.get("JAVSTORY_ACTOR_COLLECTION_LIMIT", str(cap)) or cap)))
    except ValueError:
        pass

    actor_products: Dict[str, set[str]] = defaultdict(set)

    with get_db_session_ctx() as session:
        meta_rows = session.query(
            JAVMetadata.product_code,
            JAVMetadata.actors_ko,
            JAVMetadata.actors,
        ).all()

        history_by_code: Dict[str, WatchHistory] = {}
        for h in session.query(WatchHistory).all():
            pc = str(h.product_code or "").strip().upper()
            if pc:
                history_by_code[pc] = h

        pref_by_actor: Dict[str, int] = {
            str(r.category_value or "").strip(): int(r.score or 0)
            for r in session.query(UserPreference).filter(
                UserPreference.category_type == "actor",
                UserPreference.time_slot == "all",
            ).all()
            if r.category_value
        }

    for row in meta_rows:
        pc = str(row.product_code or "").strip().upper()
        if not pc:
            continue
        for actor in _parse_comma_list(row.actors_ko or row.actors):
            actor_products[actor].add(pc)

    actors_out: List[Dict[str, Any]] = []
    for name, codes in actor_products.items():
        total = len(codes)
        if total < min_total:
            continue
        completed = 0
        watched = 0
        for pc in codes:
            h = history_by_code.get(pc)
            if not h:
                continue
            watched += 1
            if h.is_completed:
                completed += 1
        remaining = total - completed
        rate = round(completed / total, 4) if total > 0 else 0.0
        is_complete = completed >= total and total > 0
        if is_complete:
            hint = "전체 완료"
        elif remaining > 0:
            hint = f"{remaining}편 미완"
        else:
            hint = ""
        actors_out.append({
            "name": name,
            "total": total,
            "completed": completed,
            "watched": watched,
            "remaining": remaining,
            "completion_rate": rate,
            "pct": int(round(rate * 100)),
            "is_complete": is_complete,
            "hint": hint,
            "preference_score": pref_by_actor.get(name, 0),
        })

    actors_out.sort(
        key=lambda x: (
            -int(x.get("preference_score") or 0),
            -int(x.get("remaining") or 0),
            -int(x.get("total") or 0),
            x.get("name") or "",
        )
    )
    top = actors_out[:cap]

    if not top:
        return {
            "has_data": False,
            "actors": [],
            "empty_message": (
                f"배우별로 {min_total}편 이상 보유한 경우에 표시됩니다. "
                "메타데이터에 배우 정보가 있는 작품을 수집해 보세요."
            ),
        }

    return {
        "has_data": True,
        "actors": top,
        "empty_message": "",
    }


def get_monthly_genre_trend(months: int = 3) -> List[Dict[str, Any]]:
    """
    최근 N개월 시청 패턴에서 월별 장르 선호 변화를 반환합니다.
    Returns: [{"month": "2026-04", "genres": [{"name", "count"}, ...]}, ...] (최신순)
    """
    tl = get_preference_timeline("month", months, top_genres=5)
    result: List[Dict[str, Any]] = []
    for row in reversed(tl.get("series") or []):
        genres = [
            {"name": s["name"], "count": s["count"]}
            for s in row.get("stacks", [])
            if s.get("name") != "기타"
        ][:5]
        result.append({"month": row["period"], "genres": genres})
    return result


def get_library_distribution(*, force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
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
    global _DIST_CACHE
    if not force_refresh and _DIST_CACHE is not None:
        ts, cached = _DIST_CACHE
        if time.time() - ts < _DIST_CACHE_TTL_SEC:
            return cached

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

        result = {
            "actors": [{"name": k, "count": v} for k, v in actor_counter.most_common(30)],
            "genres": [{"name": k, "count": v} for k, v in genre_counter.most_common(30)],
            "makers": [{"name": k, "count": v} for k, v in maker_counter.most_common(30)],
        }
        _DIST_CACHE = (time.time(), result)
        return result


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
