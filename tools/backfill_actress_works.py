"""One-shot backfill: jav_metadata → actress_works + work_count cache.

Usage (from repo root):
    python tools/backfill_actress_works.py                  # full backfill + verify
    python tools/backfill_actress_works.py --dry-run        # stats only
    python tools/backfill_actress_works.py --counts-only    # refresh work_count + verify
    python tools/backfill_actress_works.py --verify         # verify only (no writes)
    python tools/backfill_actress_works.py --verify --sample 50
    python tools/backfill_actress_works.py --no-verify      # backfill without verify
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.harvest.database import get_db_session_ctx, init_db, ActressWork, JAVMetadata, Actress
from javstory.utils.actress_profile import (
    rebuild_all_actress_works,
    refresh_all_actress_work_counts,
    verify_actress_works_backfill,
)


def _print_stats(session) -> None:
    meta_count = session.query(JAVMetadata).count()
    link_count = session.query(ActressWork).count()
    cached_count = session.query(Actress).filter(Actress.works_updated_at.isnot(None)).count()
    actress_count = session.query(Actress).count()
    print(f"jav_metadata rows:     {meta_count}")
    print(f"actresses rows:        {actress_count}")
    print(f"actress_works rows:    {link_count}")
    print(f"work_count cached:     {cached_count}/{actress_count}")


def _print_verify_result(result: dict) -> None:
    checked = int(result.get("checked") or 0)
    print(f"Verified actresses:      {checked}")
    print(f"Count mismatches:        {len(result.get('count_mismatches') or [])}")
    print(f"Works set mismatches:    {len(result.get('works_mismatches') or [])}")
    print(f"Cache mismatches:        {len(result.get('cache_mismatches') or [])}")

    for label, key in (
        ("count", "count_mismatches"),
        ("works", "works_mismatches"),
        ("cache", "cache_mismatches"),
    ):
        samples = (result.get(key) or [])[:3]
        if not samples:
            continue
        print(f"  sample {label} diffs:")
        for item in samples:
            print(f"    {item}")

    if result.get("ok"):
        print("VERIFY OK - legacy vs indexed paths match.")
    else:
        print("VERIFY FAILED - see mismatches above.")


def _run_verify(session, sample: int | None) -> int:
    if session.query(ActressWork).count() == 0:
        print("VERIFY SKIPPED - actress_works is empty (run backfill first).")
        return 2

    result = verify_actress_works_backfill(session, sample_limit=sample)
    _print_verify_result(result)
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill actress_works from jav_metadata")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, no writes")
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Skip actress_works rebuild; refresh work_count cache only",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify only — no backfill or cache refresh",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-backfill verification",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        metavar="N",
        help="Verify only first N actresses (0 = all)",
    )
    args = parser.parse_args()

    init_db()
    sample = int(args.sample) if int(args.sample or 0) > 0 else None

    with get_db_session_ctx() as session:
        print("=== actress_works backfill ===")
        _print_stats(session)

        if args.dry_run:
            print("Dry run - no changes written.")
            return _run_verify(session, sample) if args.verify else 0

        if args.verify:
            return _run_verify(session, sample)

        if args.counts_only:
            if session.query(ActressWork).count() == 0:
                print("Counts-only skipped - actress_works is empty (run full backfill first).")
                return 2
            cached = refresh_all_actress_work_counts(session)
            session.commit()
            print(f"work_count cache refreshed: {cached}")
            if args.no_verify:
                return 0
            return _run_verify(session, sample)

        before_links = session.query(ActressWork).count()
        linked = rebuild_all_actress_works(session, source="backfill")
        refresh_all_actress_work_counts(session)
        session.commit()
        after_links = session.query(ActressWork).count()
        cached = session.query(Actress).filter(Actress.works_updated_at.isnot(None)).count()
        print(f"Links before/after:    {before_links} → {after_links} (inserted {linked})")
        print(f"work_count cached:     {cached}")

        if args.no_verify:
            return 0
        return _run_verify(session, sample)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
