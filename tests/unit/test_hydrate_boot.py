"""P2 boot hydrate: progress, skip env, marker."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from javstory.config.app_config import ENV_SKIP_BOOT_HYDRATE
from javstory.harvest.product_repository import (
    _skip_boot_hydrate,
    hydrate_all_products,
    maybe_hydrate_products_v2,
)


def test_skip_boot_hydrate_env(monkeypatch):
    monkeypatch.delenv(ENV_SKIP_BOOT_HYDRATE, raising=False)
    assert not _skip_boot_hydrate()
    monkeypatch.setenv(ENV_SKIP_BOOT_HYDRATE, "1")
    assert _skip_boot_hydrate()


def test_hydrate_all_products_progress_log():
    session = MagicMock()
    row = MagicMock()
    row.product_code = "ABC-001"
    row.folder_path = ""
    session.query.return_value.all.return_value = [row] * 3
    logs: list[str] = []

    with patch(
        "javstory.harvest.product_repository.sync_product_from_metadata_row",
    ):
        n_p, n_parts = hydrate_all_products(
            session, progress_every=2, log=logs.append
        )

    assert n_p == 3
    assert n_parts == 0
    assert any("3 works" in s for s in logs)
    assert any("progress: 2/3" in s for s in logs)


def test_maybe_hydrate_skips_when_env_set(monkeypatch, capsys):
    monkeypatch.setenv(ENV_SKIP_BOOT_HYDRATE, "1")
    maybe_hydrate_products_v2()
    out = capsys.readouterr().out
    assert "skipped at boot" in out


def test_write_hydrate_marker(tmp_path, monkeypatch):
    marker = tmp_path / "db" / ".products_v2_hydrate_done"
    monkeypatch.setattr(
        "javstory.harvest.product_repository._hydrate_marker_path",
        lambda: marker,
    )
    from javstory.harvest.product_repository import _write_hydrate_marker

    _write_hydrate_marker()
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip() == "ok"
