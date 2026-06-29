"""Favorites-only harvest — desktop FavoritesOnlyWorker parity for WebUI."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

ProgressFn = Callable[[int, int, str, str, int, str], None]  # cur, total, sku, status, pct, msg


def harvest_concurrency() -> int:
    raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
    try:
        n = int(raw) if raw else 2
    except ValueError:
        n = 2
    return max(1, min(5, n))


def _looks_invalid_page(info: object) -> bool:
    try:
        title = str(getattr(info, "title", "") or "").strip()
        code = str(getattr(info, "code", "") or "").strip()
        return (not title) and (not code)
    except Exception:
        return True


def _fetch_with_case_fallback(fetch_fn, pc: str) -> tuple[object | None, bool]:
    pc_u = (pc or "").strip().upper()
    pc_l = pc_u.lower()
    for arg in (pc_l, pc_u):
        try:
            info = fetch_fn(arg)
            if info is not None and not _looks_invalid_page(info):
                return info, True
        except Exception:
            continue
    return None, False


def process_favorite_one(pc: str) -> tuple[str, str]:
    """Returns (kind, product_code): updated | zero | failed."""
    from javstory.harvest.database import (
        JAVMetadata,
        clear_favorite_crawl_failed,
        get_db_session_ctx,
        record_favorite_crawl_failed,
        record_favorite_score_snapshot,
    )
    from javstory.harvest.scrapers.av123_scraper import fetch_video_info as av123_fetch
    from javstory.harvest.scrapers.missav123_scraper import fetch_video_info as missav_fetch

    score1, score2 = 0, 0
    d1, ok1 = _fetch_with_case_fallback(av123_fetch, pc)
    d2, ok2 = _fetch_with_case_fallback(missav_fetch, pc)
    if d1 is not None:
        score1 = int(getattr(d1, "favourite_count", 0) or 0)
    if d2 is not None:
        score2 = int(getattr(d2, "favourite_count", 0) or 0)
    total = score1 + score2
    if total == 0:
        if ok1 or ok2:
            clear_favorite_crawl_failed(pc)
            return "zero", pc
        record_favorite_crawl_failed(pc)
        return "failed", pc
    sources = f"123av:{score1},missav123:{score2}"
    with get_db_session_ctx() as session:
        row = session.query(JAVMetadata).filter_by(product_code=pc).first()
        if not row:
            record_favorite_crawl_failed(pc)
            return "failed", pc
        row.favorite_score = total
        row.favorite_sources = sources
        row.favorite_crawl_failed_at = None
        session.commit()
    record_favorite_score_snapshot(pc, total, sources)
    return "updated", pc


def resolve_favorite_codes(mode: str, codes: list[str] | None = None) -> list[str]:
    from sqlalchemy import or_

    from javstory.harvest.database import (
        JAVMetadata,
        favorite_crawl_failure_cutoff,
        get_db_session_ctx,
    )

    mode = (mode or "selected").strip().lower()
    if mode == "selected":
        return [str(c).strip().upper() for c in (codes or []) if str(c).strip()]

    co = favorite_crawl_failure_cutoff()
    with get_db_session_ctx() as session:
        q = session.query(JAVMetadata.product_code)
        if mode == "missing":
            q = q.filter(
                or_(
                    JAVMetadata.favorite_sources.is_(None),
                    JAVMetadata.favorite_sources == "",
                )
            )
        if co is not None:
            q = q.filter(
                or_(
                    JAVMetadata.favorite_crawl_failed_at.is_(None),
                    JAVMetadata.favorite_crawl_failed_at < co,
                )
            )
        return [r[0] for r in q.all()]


def run_favorites_batch(
    product_codes: list[str],
    *,
    on_progress: ProgressFn | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    codes = [str(c).strip().upper() for c in product_codes if str(c).strip()]
    total = len(codes)
    updated = zero = failed = 0
    stop = should_stop or (lambda: False)
    workers = harvest_concurrency()
    done = 0
    prog = on_progress or (lambda *_: None)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_favorite_one, pc): pc for pc in codes}
        for fut in as_completed(futs):
            if stop():
                break
            pc = futs[fut]
            try:
                kind, _ = fut.result()
                if kind == "updated":
                    updated += 1
                    prog(done + 1, total, pc, "done", 100, f"♥ 갱신")
                elif kind == "zero":
                    zero += 1
                    prog(done + 1, total, pc, "done", 100, "0점")
                else:
                    failed += 1
                    prog(done + 1, total, pc, "error", 100, "실패")
            except Exception as e:
                failed += 1
                prog(done + 1, total, pc, "error", 100, str(e))
            done += 1
    return {"updated": updated, "zero": zero, "failed": failed, "total": total}
