"""주간 취향 리포트 (Weekly Digest) — 지난 7일 감상 요약."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from javstory.harvest.database import JAVMetadata, WatchHistory, get_db_session_ctx

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "weekly_digest.json"


def _parse_comma_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


def _load_excluded_genres() -> set[str]:
    from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES

    excluded_str = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
    if excluded_str:
        return {v.strip() for v in excluded_str.split(",") if v.strip()}
    return set(SIMILARITY_EXCLUDED_GENRES)


def _period_bounds(days: int = 7) -> Tuple[datetime, datetime, datetime, datetime]:
    """이번 집계 구간(최근 N일)과 직전 N일."""
    end = datetime.now()
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    prev_end = start - timedelta(seconds=1)
    prev_start = (prev_end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end, prev_start, prev_end


def _week_label(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.year}년 {start.month}월 {start.day}~{end.day}일"
    return f"{start.strftime('%Y.%m.%d')} ~ {end.strftime('%Y.%m.%d')}"


def _histories_in_range(
    start: datetime,
    end: datetime,
) -> list[WatchHistory]:
    with get_db_session_ctx() as session:
        return (
            session.query(WatchHistory)
            .filter(
                WatchHistory.updated_at >= start,
                WatchHistory.updated_at <= end,
            )
            .all()
        )


def _aggregate_week(
    histories: list[WatchHistory],
    excluded: set[str],
) -> Dict[str, Any]:
    """주간 시청 집계: 편수, 배우, 장르."""
    if not histories:
        return {
            "watched_count": 0,
            "completed_count": 0,
            "actors": Counter(),
            "genres": Counter(),
        }

    pcs = list({str(h.product_code or "").strip().upper() for h in histories if h.product_code})
    meta_by_code: Dict[str, JAVMetadata] = {}
    with get_db_session_ctx() as session:
        if pcs:
            for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(pcs)).all():
                pc = str(row.product_code or "").strip().upper()
                if pc:
                    meta_by_code[pc] = row

    actors: Counter = Counter()
    genres: Counter = Counter()
    completed = 0
    seen_pc: set[str] = set()

    for h in histories:
        pc = str(h.product_code or "").strip().upper()
        if not pc or pc in seen_pc:
            continue
        seen_pc.add(pc)
        if h.is_completed:
            completed += 1
        row = meta_by_code.get(pc)
        if not row:
            continue
        for a in _parse_comma_list(row.actors_ko or row.actors):
            actors[a] += 1
        for g in _parse_comma_list(row.genres_ko or row.genres):
            if g not in excluded:
                genres[g] += 1

    return {
        "watched_count": len(seen_pc),
        "completed_count": completed,
        "actors": actors,
        "genres": genres,
    }


def _detect_new_taste(
    cur_genres: Counter,
    prev_genres: Counter,
) -> str:
    if not cur_genres:
        return ""
    deltas: List[Tuple[str, int]] = []
    for name, count in cur_genres.items():
        delta = count - prev_genres.get(name, 0)
        if delta > 0:
            deltas.append((name, delta))
    if not deltas:
        top = cur_genres.most_common(1)
        return f"『{top[0][0]}』 장르를 많이 보셨습니다" if top else ""
    deltas.sort(key=lambda x: (-x[1], -cur_genres[x[0]]))
    name, delta = deltas[0]
    if prev_genres.get(name, 0) == 0:
        return f"새로 『{name}』 장르를 탐색하기 시작했습니다"
    return f"『{name}』 장르 비중이 지난주보다 +{delta}편"


def _build_lines(payload: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    wc = int(payload.get("watched_count") or 0)
    delta = payload.get("watched_delta")
    if wc <= 0:
        lines.append("이번 주 시청 기록이 없습니다.")
        return lines

    if delta is None:
        lines.append(f"이번 주 {wc}편 감상")
    elif delta > 0:
        lines.append(f"이번 주 {wc}편 감상 (지난주보다 +{delta}편)")
    elif delta < 0:
        lines.append(f"이번 주 {wc}편 감상 (지난주보다 {delta}편)")
    else:
        lines.append(f"이번 주 {wc}편 감상 (지난주와 동일)")

    top_actor = payload.get("top_actor") or {}
    if top_actor.get("name"):
        lines.append(f"가장 많이 본 배우: {top_actor['name']} ({top_actor.get('count', 0)}편)")

    new_taste = str(payload.get("new_taste") or "").strip()
    if new_taste:
        lines.append(new_taste)

    rec = payload.get("recommendation") or {}
    if rec.get("product_code"):
        pct = int(round(float(rec.get("rec_score") or 0) * 100))
        title = rec.get("title_ko") or rec["product_code"]
        lines.append(f"추천 다음 작품: {rec['product_code']} — {title} (일치 {pct}%)")

    return lines


def generate_weekly_digest(
    *,
    days: int = 7,
    excluded: set[str] | None = None,
) -> Dict[str, Any]:
    """주간 리포트 생성 및 캐시 저장."""
    excl = excluded if excluded is not None else _load_excluded_genres()
    start, end, prev_start, prev_end = _period_bounds(days)

    cur_h = _histories_in_range(start, end)
    prev_h = _histories_in_range(prev_start, prev_end)
    cur = _aggregate_week(cur_h, excl)
    prev = _aggregate_week(prev_h, excl)

    watched = int(cur["watched_count"])
    prev_watched = int(prev["watched_count"])
    delta = watched - prev_watched if prev_watched > 0 or watched > 0 else None

    top_actor = {}
    if cur["actors"]:
        name, count = cur["actors"].most_common(1)[0]
        top_actor = {"name": name, "count": count}

    new_taste = _detect_new_taste(cur["genres"], prev["genres"])

    recommendation: Dict[str, Any] = {}
    try:
        from javstory.analytics.preference_engine import get_recommendations

        recs = get_recommendations(1)
        if recs:
            recommendation = recs[0]
    except Exception:
        pass

    period_key = f"{start.date().isoformat()}_{end.date().isoformat()}"
    payload: Dict[str, Any] = {
        "has_data": watched > 0,
        "period_key": period_key,
        "week_label": _week_label(start, end),
        "week_start": start.date().isoformat(),
        "week_end": end.date().isoformat(),
        "watched_count": watched,
        "watched_delta": delta,
        "completed_count": int(cur["completed_count"]),
        "top_actor": top_actor,
        "new_taste": new_taste,
        "recommendation": recommendation,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "empty_message": "이번 주 시청 이력이 없습니다. 재생 후 주간 리포트가 생성됩니다.",
    }
    payload["lines"] = _build_lines(payload)

    _save_cache(payload)
    return payload


def _save_cache(payload: Dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _load_cache() -> Dict[str, Any] | None:
    if not _CACHE_PATH.is_file():
        return None
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _cache_fresh(cached: Dict[str, Any], days: int = 7) -> bool:
    start, end, _, _ = _period_bounds(days)
    if cached.get("period_key") == f"{start.date().isoformat()}_{end.date().isoformat()}":
        return True
    gen = cached.get("generated_at") or ""
    try:
        ts = datetime.fromisoformat(str(gen))
        return datetime.now() - ts < timedelta(hours=12)
    except (TypeError, ValueError):
        return False


def get_weekly_digest(
    force_refresh: bool = False,
    *,
    days: int = 7,
    excluded: set[str] | None = None,
) -> Dict[str, Any]:
    """
    주간 리포트 반환. 기간이 바뀌었거나 force_refresh 시 재생성.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached and _cache_fresh(cached, days):
            if "lines" not in cached:
                cached["lines"] = _build_lines(cached)
            return cached

    return generate_weekly_digest(days=days, excluded=excluded)
