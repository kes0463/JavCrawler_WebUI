"""User-rated product list queries for Persona Chat."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import or_

from javstory.harvest.database import JAVMetadata, WatchHistory, get_db_session_ctx
from javstory.persona.library_search import _attach_user_watch_signals, row_to_search_result

_RATING_LIST_HINTS = (
    "점수 준",
    "점수준",
    "별점 준",
    "별점준",
    "평점 준",
    "평점준",
    "내가 점수",
    "내가 별점",
    "내가 평점",
    "평가한 작품",
    "평가 한 작품",
    "점수 부여",
    "별점 부여",
    "평점 부여",
    "줬던 작품",
    "준 작품",
    "rating",
    "rated",
)

_LIST_ACTION_HINTS = (
    "목록",
    "리스트",
    "알려",
    "보여",
    "나열",
    "뭐야",
    "뭐 있",
    "어떤 작품",
    "정리",
    "줘",
    "해줘",
)


def is_user_rating_list_request(text: str) -> bool:
    """Return True when the user asks for their personally rated/scored works."""
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False
    if not any(hint in lowered for hint in _RATING_LIST_HINTS):
        return False
    if any(hint in lowered for hint in _LIST_ACTION_HINTS):
        return True
    return any(h in lowered for h in ("점수", "별점", "평점")) and any(
        h in lowered for h in ("작품", "리스트", "목록")
    )


def fetch_user_rated_products(*, limit: int = 40) -> List[Dict[str, Any]]:
    """Return works the user explicitly rated or strongly marked (liked/completed)."""
    cap = max(1, min(80, int(limit or 40)))
    rows: List[tuple[WatchHistory, JAVMetadata | None]] = []

    with get_db_session_ctx() as session:
        histories = (
            session.query(WatchHistory)
            .filter(
                or_(
                    WatchHistory.rating > 0,
                    WatchHistory.liked == True,  # noqa: E712
                    WatchHistory.is_completed == True,  # noqa: E712
                )
            )
            .order_by(WatchHistory.rating.desc(), WatchHistory.updated_at.desc())
            .limit(cap * 2)
            .all()
        )
        codes = [str(h.product_code or "").strip().upper() for h in histories if h.product_code]
        meta_by_code: Dict[str, JAVMetadata] = {}
        if codes:
            for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(codes)).all():
                meta_by_code[str(row.product_code or "").strip().upper()] = row

        for history in histories:
            pc = str(history.product_code or "").strip().upper()
            if not pc:
                continue
            rows.append((history, meta_by_code.get(pc)))

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for history, meta in rows:
        pc = str(history.product_code or "").strip().upper()
        if not pc or pc in seen:
            continue
        seen.add(pc)
        if meta is not None:
            item = row_to_search_result(meta, source="user_rating", score=1.0)
        else:
            item = {
                "product_code": pc,
                "title_ko": "",
                "title_ja": "",
                "actors": [],
                "genres": [],
                "maker": "",
                "release_date": "",
                "synopsis": "",
                "favorite_score": 0,
                "folder_path": "",
                "source": "user_rating",
                "score": 1.0,
            }
        item["user_rating"] = int(history.rating or 0)
        item["user_liked"] = bool(history.liked)
        item["user_disliked"] = bool(history.disliked)
        item["user_is_completed"] = bool(history.is_completed)
        item["rated_at"] = str(history.updated_at or "")
        out.append(item)
        if len(out) >= cap:
            break

    _attach_user_watch_signals(out)
    return out
