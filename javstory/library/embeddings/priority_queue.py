"""Priority embedding build queue for recommendation hot paths."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Sequence

from javstory.harvest.database import JAVMetadata, WatchHistory, get_db_session_ctx
from javstory.library.embeddings.pipeline import (
    build_and_store_embeddings_for_product,
    embeddings_enabled_from_env,
    embeddings_ollama_model_from_env,
)
from javstory.library.embeddings.store import embeddings_cache_path
from javstory.persona.library_search import normalize_product_code
from javstory.translation.story_grok_module import story_context_cache_path_grok


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _embedding_needs_build(product_code: str, *, model: str) -> bool:
    pc = normalize_product_code(product_code)
    if not pc:
        return False
    path = embeddings_cache_path(pc, model=model)
    if not path.is_file():
        return True
    try:
        story_path = story_context_cache_path_grok(pc)
        if story_path.is_file() and story_path.stat().st_mtime > path.stat().st_mtime:
            return True
    except OSError:
        pass
    return False


def collect_recommendation_embedding_priorities(
    *,
    extra_codes: Sequence[str] | None = None,
    limit: int = 48,
) -> List[str]:
    """
    Tiered product codes for embedding warmup:
    1) liked / rating 4+
    2) caller-supplied seeds (strong reactions, pool results)
    3) recent high-engagement incomplete watches
    4) works with Grok story cache
    """
    cap = max(8, min(96, int(limit or 48)))
    ordered: List[str] = []
    seen: set[str] = set()

    def _add(code: str) -> None:
        pc = normalize_product_code(code)
        if not pc or pc in seen:
            return
        seen.add(pc)
        ordered.append(pc)

    for code in extra_codes or []:
        _add(str(code))
        if len(ordered) >= cap:
            return ordered[:cap]

    cutoff = _utc_now() - timedelta(days=90)
    try:
        with get_db_session_ctx() as session:
            liked_rows = (
                session.query(WatchHistory.product_code)
                .filter(WatchHistory.liked.is_(True))
                .order_by(WatchHistory.updated_at.desc())
                .limit(24)
                .all()
            )
            for (code,) in liked_rows:
                _add(str(code or ""))
                if len(ordered) >= cap:
                    return ordered[:cap]

            rated_rows = (
                session.query(WatchHistory.product_code, WatchHistory.rating)
                .filter(WatchHistory.rating >= 4)
                .order_by(WatchHistory.rating.desc(), WatchHistory.updated_at.desc())
                .limit(24)
                .all()
            )
            for code, _rating in rated_rows:
                _add(str(code or ""))
                if len(ordered) >= cap:
                    return ordered[:cap]

            recent_rows = (
                session.query(
                    WatchHistory.product_code,
                    WatchHistory.watch_duration,
                    WatchHistory.total_duration,
                    WatchHistory.is_completed,
                )
                .filter(WatchHistory.updated_at >= cutoff)
                .order_by(WatchHistory.updated_at.desc())
                .limit(80)
                .all()
            )
            for code, watched, total, completed in recent_rows:
                if completed:
                    continue
                total_i = int(total or 0)
                watched_i = int(watched or 0)
                if total_i > 0 and watched_i / max(1, total_i) >= 0.35:
                    _add(str(code or ""))
                if len(ordered) >= cap:
                    return ordered[:cap]

            if len(ordered) < cap:
                meta_rows = (
                    session.query(JAVMetadata.product_code)
                    .order_by(JAVMetadata.favorite_score.desc())
                    .limit(120)
                    .all()
                )
                for (code,) in meta_rows:
                    pc = normalize_product_code(str(code or ""))
                    if not pc:
                        continue
                    if story_context_cache_path_grok(pc).is_file():
                        _add(pc)
                    if len(ordered) >= cap:
                        break
    except Exception:
        pass

    return ordered[:cap]


def ensure_priority_embeddings_async(
    codes: Iterable[str],
    *,
    max_batch: int = 6,
    logger_func: Any = None,
) -> None:
    """Fire-and-forget embedding builds for missing/stale priority codes."""
    if not embeddings_enabled_from_env():
        return
    model = embeddings_ollama_model_from_env()
    pending = [
        pc
        for pc in dict.fromkeys(normalize_product_code(c) or "" for c in codes)
        if pc and _embedding_needs_build(pc, model=model)
    ][: max(1, min(12, int(max_batch or 6)))]
    if not pending:
        return

    def _worker(batch: List[str]) -> None:
        import asyncio

        async def _run() -> None:
            for pc in batch:
                try:
                    await build_and_store_embeddings_for_product(
                        pc,
                        model=model,
                        logger_func=logger_func,
                    )
                except Exception:
                    continue

        try:
            asyncio.run(_run())
        except Exception:
            pass

    threading.Thread(target=_worker, args=(pending,), daemon=True, name="embedding-priority").start()
