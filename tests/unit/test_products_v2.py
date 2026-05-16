"""DB v2 P2 — products / video_files / product_repository."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from javstory.library.media_parts import build_video_part_refs


def _reload_db(monkeypatch, db_path: Path):
    import javstory.config.app_config as app_config

    monkeypatch.setattr(app_config, "DB_PATH", db_path)
    import javstory.harvest.database as dbmod

    importlib.reload(dbmod)
    return dbmod


def test_migration_creates_products_tables(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "p2.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()
    with sqlite3.connect(db_path) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "products" in tables
    assert "video_files" in tables
    assert dbmod.get_schema_user_version() >= 10


def test_sync_video_files_matches_media_parts(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "sync.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()

    bind = tmp_path / "ABC-123"
    bind.mkdir()
    p1 = bind / "ABC-123_PART1.mp4"
    p2 = bind / "ABC-123_PART2.mp4"
    p1.write_bytes(b"a")
    p2.write_bytes(b"b")

    from javstory.harvest.product_repository import (
        set_folder_path,
        sync_product_from_metadata_row,
        sync_video_files,
    )

    with dbmod.get_db_session_ctx() as session:
        row = dbmod.JAVMetadata(product_code="ABC-123")
        session.add(row)
        session.flush()
        sync_product_from_metadata_row(session, row)
        set_folder_path(session, "ABC-123", str(bind))
        sync_video_files(session, "ABC-123", bind, [p2, p1])
        session.commit()

    refs, _ = build_video_part_refs(bind, [p2, p1])
    with dbmod.get_db_session_ctx() as session:
        prod = session.query(dbmod.Product).filter_by(sku="ABC-123").one()
        vfs = (
            session.query(dbmod.VideoFile)
            .filter_by(product_id=prod.id)
            .order_by(dbmod.VideoFile.part_order)
            .all()
        )
    assert len(vfs) == len(refs)
    for vf, ref in zip(vfs, refs):
        assert vf.part_order == ref.order
        assert vf.video_relpath == ref.video_relpath.replace("\\", "/")


def test_db_v2_read_paths(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "read.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()

    bind = tmp_path / "TST-001"
    bind.mkdir()
    only = bind / "TST-001.mp4"
    only.write_bytes(b"x")

    from javstory.harvest.product_repository import (
        get_video_absolute_paths,
        set_folder_path,
        sync_product_from_metadata_row,
        sync_video_files,
    )

    with dbmod.get_db_session_ctx() as session:
        row = dbmod.JAVMetadata(product_code="TST-001", folder_path=str(bind))
        session.add(row)
        session.flush()
        sync_product_from_metadata_row(session, row)
        set_folder_path(session, "TST-001", str(bind))
        sync_video_files(session, "TST-001", bind, [only])
        session.commit()

    monkeypatch.setenv("JAVSTORY_DB_V2_READ", "1")
    paths = get_video_absolute_paths("TST-001")
    assert len(paths) == 1
    assert paths[0].resolve() == only.resolve()
