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
