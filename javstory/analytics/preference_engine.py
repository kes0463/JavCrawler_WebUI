"""
사용자 취향 분석 엔진 (Preference Engine)

기능:
- score_preferences(product_code): 작품의 배우/장르/제작사를 파싱하여 UserPreference 점수 업데이트
- get_top_actors/genres/makers(n): TOP N 선호 항목 반환
- compute_recent_trend(days): 최근 N일 가중 점수로 취향 변화 감지
- get_time_slot(hour): 현재 시간 → 'morning'/'afternoon'/'night'
- get_recommendation_score(product_code): 미시청 작품의 취향 일치도 계산
"""
from __future__ import annotations

import datetime
from typing import List, Dict, Any

from javstory.harvest.database import get_db_session_ctx, JAVMetadata, WatchHistory, UserPreference


# ── 시간대 분류 ──────────────────────────────────────────────────────────────

def get_time_slot(hour: int | None = None) -> str:
    """시각(0~23) → 시간대 문자열."""
    if hour is None:
        hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 19:
        return "afternoon"
    return "night"  # 19~04시


# ── 선호도 점수 업데이트 ─────────────────────────────────────────────────────

def _parse_comma(text: str | None) -> List[str]:
    """쉼표 또는 공백 구분 텍스트를 리스트로 파싱."""
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


def _upsert_preference(session, category_type: str, value: str, delta: int = 1,
                        recent_delta: int | None = None, time_slot: str = "all") -> None:
    """UserPreference 점수를 증가(또는 감소)시킵니다."""
    if not value:
        return
    if recent_delta is None:
        recent_delta = delta

    # time_slot='all' 통합 레코드
    pref = session.query(UserPreference).filter_by(
        category_type=category_type,
        category_value=value,
        time_slot="all",
    ).first()
    if not pref:
        pref = UserPreference(
            category_type=category_type,
            category_value=value,
            score=max(0, delta),
            recent_score=max(0, recent_delta),
            time_slot="all",
            last_watched_at=datetime.datetime.now(),
        )
        session.add(pref)
    else:
        pref.score = max(0, pref.score + delta)
        pref.recent_score = max(0, pref.recent_score + recent_delta)
        pref.last_watched_at = datetime.datetime.now()

    # time_slot 분리 레코드
    if time_slot != "all":
        ts_pref = session.query(UserPreference).filter_by(
            category_type=category_type,
            category_value=value,
            time_slot=time_slot,
        ).first()
        if not ts_pref:
            ts_pref = UserPreference(
                category_type=category_type,
                category_value=value,
                score=max(0, delta),
                recent_score=max(0, recent_delta),
                time_slot=time_slot,
                last_watched_at=datetime.datetime.now(),
            )
            session.add(ts_pref)
        else:
            ts_pref.score = max(0, ts_pref.score + delta)
            ts_pref.recent_score = max(0, ts_pref.recent_score + recent_delta)
            ts_pref.last_watched_at = datetime.datetime.now()


def score_preferences(product_code: str, *, delta: int = 1,
                       time_slot: str | None = None) -> None:
    """
    작품의 배우/장르/제작사 메타데이터를 바탕으로 UserPreference 점수를 업데이트합니다.
    호출 시점: 재생 완료, 좋아요, 세션 종료 등

    Args:
        product_code: 품번 (예: "ABC-123")
        delta: 점수 증감량 (+1=좋아요, -2=싫어요 등)
        time_slot: 'morning'|'afternoon'|'night'|None(자동 감지)
    """
    if not product_code:
        return
    ts = time_slot or get_time_slot()
    pc = product_code.strip().upper()

    with get_db_session_ctx() as session:
        row = session.query(JAVMetadata).filter_by(product_code=pc).first()
        if not row:
            return

        actors = _parse_comma(row.actors_ko or row.actors_ja or row.actors or "")
        genres = _parse_comma(row.genres_ko or row.genres or "")
        maker = (row.maker_ko or row.maker_ja or row.maker or "").strip()

        for actor in actors:
            _upsert_preference(session, "actor", actor, delta=delta, time_slot=ts)
        for genre in genres:
            _upsert_preference(session, "genre", genre, delta=delta, time_slot=ts)
        if maker:
            _upsert_preference(session, "maker", maker, delta=delta, time_slot=ts)

        session.commit()


# ── 취향 변화 감지 (최근 7일 recent_score 감쇠 갱신) ────────────────────────

def decay_recent_scores(decay_factor: float = 0.8) -> None:
    """
    최근 7일 이내에 업데이트되지 않은 recent_score를 감쇠합니다.
    배치 실행용. 매일 1회 권장.
    """
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    with get_db_session_ctx() as session:
        prefs = session.query(UserPreference).filter(
            UserPreference.last_watched_at < cutoff,
            UserPreference.recent_score > 0,
        ).all()
        for p in prefs:
            p.recent_score = max(0, int(p.recent_score * decay_factor))
        session.commit()


# ── TOP N 조회 ────────────────────────────────────────────────────────────────

def _get_top(category_type: str, n: int = 5,
             use_recent: bool = False,
             time_slot: str = "all") -> List[Dict[str, Any]]:
    """내부 공통 TOP N 조회."""
    with get_db_session_ctx() as session:
        q = session.query(UserPreference).filter(
            UserPreference.category_type == category_type,
            UserPreference.time_slot == time_slot,
        )
        if use_recent:
            q = q.order_by(UserPreference.recent_score.desc(), UserPreference.score.desc())
        else:
            q = q.order_by(UserPreference.score.desc())
        rows = q.limit(n).all()
        return [
            {
                "name": r.category_value,
                "score": r.score,
                "recent_score": r.recent_score,
                "last_watched_at": r.last_watched_at.isoformat() if r.last_watched_at else "",
            }
            for r in rows
        ]


def get_top_actors(n: int = 5, use_recent: bool = False) -> List[Dict[str, Any]]:
    return _get_top("actor", n, use_recent=use_recent)


def get_top_genres(n: int = 8, use_recent: bool = False) -> List[Dict[str, Any]]:
    return _get_top("genre", n, use_recent=use_recent)


def get_top_makers(n: int = 5, use_recent: bool = False) -> List[Dict[str, Any]]:
    return _get_top("maker", n, use_recent=use_recent)


def compute_recent_trend(days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
    """
    최근 N일 기준 취향 변화를 반환합니다.
    Returns: {"actors": [...], "genres": [...]}
    """
    return {
        "actors": get_top_actors(5, use_recent=True),
        "genres": get_top_genres(5, use_recent=True),
    }


# ── 추천 지수 계산 ────────────────────────────────────────────────────────────

def get_recommendation_score(product_code: str) -> float:
    """
    특정 작품이 사용자 취향과 얼마나 일치하는지 0.0~1.0 점수를 반환합니다.
    배우/장르/제작사 점수를 가중 합산합니다.
    """
    pc = (product_code or "").strip().upper()
    if not pc:
        return 0.0

    with get_db_session_ctx() as session:
        row = session.query(JAVMetadata).filter_by(product_code=pc).first()
        if not row:
            return 0.0

        actors = _parse_comma(row.actors_ko or row.actors_ja or row.actors or "")
        genres = _parse_comma(row.genres_ko or row.genres or "")
        maker = (row.maker_ko or row.maker_ja or row.maker or "").strip()

        actor_score = 0
        genre_score = 0
        maker_score = 0
        actor_max = 0
        genre_max = 0
        maker_max = 0

        # 배우 점수 (40% 가중)
        if actors:
            all_actor_prefs = session.query(UserPreference).filter_by(
                category_type="actor", time_slot="all"
            ).order_by(UserPreference.score.desc()).limit(20).all()
            actor_max = max((p.score for p in all_actor_prefs), default=1) or 1
            for actor in actors:
                p = session.query(UserPreference).filter_by(
                    category_type="actor", category_value=actor, time_slot="all"
                ).first()
                if p:
                    actor_score += p.score

        # 장르 점수 (40% 가중)
        if genres:
            all_genre_prefs = session.query(UserPreference).filter_by(
                category_type="genre", time_slot="all"
            ).order_by(UserPreference.score.desc()).limit(20).all()
            genre_max = max((p.score for p in all_genre_prefs), default=1) or 1
            for genre in genres:
                p = session.query(UserPreference).filter_by(
                    category_type="genre", category_value=genre, time_slot="all"
                ).first()
                if p:
                    genre_score += p.score

        # 제작사 점수 (20% 가중)
        if maker:
            all_maker_prefs = session.query(UserPreference).filter_by(
                category_type="maker", time_slot="all"
            ).order_by(UserPreference.score.desc()).limit(10).all()
            maker_max = max((p.score for p in all_maker_prefs), default=1) or 1
            p = session.query(UserPreference).filter_by(
                category_type="maker", category_value=maker, time_slot="all"
            ).first()
            if p:
                maker_score = p.score

        # 정규화 가중 합산
        a_norm = min(1.0, (actor_score / (actor_max * max(len(actors), 1))) if actor_max > 0 else 0.0)
        g_norm = min(1.0, (genre_score / (genre_max * max(len(genres), 1))) if genre_max > 0 else 0.0)
        m_norm = min(1.0, maker_score / maker_max if maker_max > 0 else 0.0)

        return round(a_norm * 0.4 + g_norm * 0.4 + m_norm * 0.2, 4)
