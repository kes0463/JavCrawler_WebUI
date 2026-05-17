#!/usr/bin/env python3
"""jav_metadata -> products / video_files backfill (DB v2 P2)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.harvest.database import get_db_session_ctx, init_db, upgrade_alembic_head
from javstory.harvest.product_repository import (
    _write_hydrate_marker,
    hydrate_all_products,
)


def main() -> int:
    init_db()
    if not upgrade_alembic_head(strict=True):
        raise SystemExit("Alembic upgrade failed — see logs/db_upgrade_recovery.txt")
    with get_db_session_ctx() as session:
        n_products, n_parts = hydrate_all_products(session)
        session.commit()
    _write_hydrate_marker()
    print(f"hydrate complete: {n_products} products, {n_parts} video file parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
