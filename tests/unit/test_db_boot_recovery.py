"""DB boot — Alembic failure read-only path."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_db(monkeypatch, db_path: Path):
    import javstory.config.app_config as app_config

    monkeypatch.setattr(app_config, "DB_PATH", db_path)
    import javstory.harvest.database as dbmod

    return importlib.reload(dbmod)


def test_upgrade_failure_sets_read_only(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "jav.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_db()

    def _boom(*_a, **_k):
        raise RuntimeError("alembic broken")

    def _fail_upgrade(**_kw):
        dbmod._db_boot_mode = "read_only"
        dbmod._last_boot_result = dbmod.DbBootResult(
            ok=False,
            read_only=True,
            message="test fail",
            backup_path=None,
            recovery_log=str(tmp_path / "recovery.txt"),
        )
        return False

    monkeypatch.setattr(dbmod, "upgrade_alembic_head", _fail_upgrade)

    result = dbmod.init_and_upgrade_db()
    assert result.read_only is True
    assert dbmod.is_db_read_only() is True

    with pytest.raises(dbmod.DbReadOnlyError):
        dbmod.assert_db_writable("test")

    # 다른 unit 테스트에 read-only 전역 상태가 새지 않도록 복구
    dbmod._db_boot_mode = "ok"
    dbmod._last_boot_result = None
