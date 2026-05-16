"""Alembic migrations — P1 stamp + P2 products."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

V8_TABLES = frozenset(
    {
        "jav_metadata",
        "actresses",
        "genres",
        "makers",
        "background_cache",
        "watch_history",
        "favorite_score_history",
        "user_preferences",
    }
)

V8_INDEXES = frozenset(
    {
        "idx_jav_metadata_updated_at",
        "idx_jav_metadata_analysis_status",
        "idx_jav_metadata_release_date",
        "idx_jav_metadata_folder_path",
        "idx_jav_favorite_score",
        "idx_fav_hist_pc_time",
    }
)


def _reload_database_module(monkeypatch, db_path: Path):
    import javstory.config.app_config as app_config

    monkeypatch.setattr(app_config, "DB_PATH", db_path)
    import javstory.harvest.database as dbmod

    importlib.reload(dbmod)
    return dbmod


def _alembic_cfg(dbmod) -> Config:
    root = Path(dbmod.__file__).resolve().parents[2]
    return Config(str(root / "alembic.ini"))


def _list_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _list_indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name IS NOT NULL"
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def test_alembic_stamp_only_fresh_db(tmp_path: Path, monkeypatch) -> None:
    """P1: 0001_stamp_v8 — DDL 없음, user_version 9."""
    db_path = tmp_path / "fresh.db"
    dbmod = _reload_database_module(monkeypatch, db_path)
    dbmod.init_db()
    assert dbmod.get_schema_user_version() == 8

    with sqlite3.connect(db_path) as conn:
        tables_before = _list_tables(conn)

    command.upgrade(_alembic_cfg(dbmod), "0001_stamp_v8")
    assert dbmod.get_schema_user_version() == 9

    with sqlite3.connect(db_path) as conn:
        tables_after = _list_tables(conn)
        assert V8_TABLES <= tables_after
        assert tables_before <= tables_after
        assert "products" not in tables_after
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert rev is not None and rev[0] == "0001_stamp_v8"
        assert V8_INDEXES <= _list_indexes(conn)


def test_alembic_upgrade_head_includes_p2(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "head.db"
    dbmod = _reload_database_module(monkeypatch, db_path)
    dbmod.init_db()
    dbmod.upgrade_alembic_head()
    assert dbmod.get_schema_user_version() >= 10

    with sqlite3.connect(db_path) as conn:
        tables = _list_tables(conn)
        assert V8_TABLES <= tables
        assert "products" in tables
        assert "video_files" in tables
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert rev[0] == "0002_add_products_video_files"


def test_alembic_idempotent_after_head(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "idem.db"
    dbmod = _reload_database_module(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()
    ver = dbmod.get_schema_user_version()
    dbmod.init_db()
    dbmod.upgrade_alembic_head()
    assert dbmod.get_schema_user_version() == ver
