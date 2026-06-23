"""Post-recommendation feedback loop for Persona Chat memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Sequence

from javstory.harvest.database import WatchHistory, get_db_session_ctx
from javstory.persona.library_search import normalize_product_code


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def register_recommendation_outcomes(memory_store: Any, product_codes: Sequence[str]) -> None:
    """Track assistant-recommended codes for later watch/rating feedback."""
    if memory_store is None:
        return
    pending = list(getattr(memory_store, "pending_recommendation_outcomes", None) or [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    seen = {
        normalize_product_code(str(item.get("product_code") or ""))
        for item in pending
        if isinstance(item, dict)
    }
    for code in product_codes:
        pc = normalize_product_code(str(code or ""))
        if not pc or pc in seen:
            continue
        pending.append({"product_code": pc, "recommended_at": now})
        seen.add(pc)
    if len(pending) > 48:
        pending = pending[-48:]
    memory_store.pending_recommendation_outcomes = pending


def sync_recommendation_watch_feedback(memory_store: Any, *, hours: int = 24) -> None:
    """
    Close the feedback loop:
    - recommended code watched within window -> implicit positive note
    - recommended code rated 1-2 -> negative feedback note
    """
    if memory_store is None:
        return
    pending = [
        dict(item)
        for item in (getattr(memory_store, "pending_recommendation_outcomes", None) or [])
        if isinstance(item, dict)
    ]
    if not pending:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours or 24)))
    codes = [normalize_product_code(str(item.get("product_code") or "")) for item in pending]
    codes = [c for c in codes if c]
    if not codes:
        return

    rows: List[WatchHistory] = []
    try:
        with get_db_session_ctx() as session:
            rows = (
                session.query(WatchHistory)
                .filter(WatchHistory.product_code.in_(codes))
                .all()
            )
    except Exception:
        return

    row_by_code = {
        normalize_product_code(str(row.product_code or "")): row
        for row in rows
        if normalize_product_code(str(row.product_code or ""))
    }

    strong_notes = list(getattr(memory_store, "strong_reaction_notes", None) or [])
    negative_notes = list(getattr(memory_store, "negative_feedback_notes", None) or [])
    max_notes = int(getattr(memory_store, "max_notes", 24) or 24)
    remaining: List[dict] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for item in pending:
        pc = normalize_product_code(str(item.get("product_code") or ""))
        if not pc:
            continue
        recommended_at = _parse_iso(str(item.get("recommended_at") or ""))
        row = row_by_code.get(pc)
        if row is None:
            remaining.append(item)
            continue
        updated_at = getattr(row, "updated_at", None)
        if updated_at is not None and getattr(updated_at, "tzinfo", None) is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if recommended_at and updated_at and updated_at < recommended_at:
            remaining.append(item)
            continue

        rating = int(getattr(row, "rating", 0) or 0)
        liked = bool(getattr(row, "liked", False))
        disliked = bool(getattr(row, "disliked", False))
        watched = int(getattr(row, "watch_duration", 0) or 0)
        completed = bool(getattr(row, "is_completed", False))

        if disliked or (0 < rating <= 2):
            negative_notes.append(
                {
                    "text": f"추천 후 낮은 평가: {pc}",
                    "product_codes": [pc],
                    "source": "post_rec_rating",
                    "created_at": now,
                }
            )
            continue

        if liked or rating >= 4 or completed or watched >= 300:
            strong_notes.append(
                {
                    "text": f"추천 후 시청/호응: {pc}",
                    "product_codes": [pc],
                    "source": "implicit_watch",
                    "intensity": 6 if liked or rating >= 4 else 4,
                    "created_at": now,
                }
            )
            continue

        if recommended_at and recommended_at >= cutoff:
            remaining.append(item)

    memory_store.strong_reaction_notes = strong_notes[-max_notes:]
    memory_store.negative_feedback_notes = negative_notes[-max_notes:]
    memory_store.pending_recommendation_outcomes = remaining[-48:]
