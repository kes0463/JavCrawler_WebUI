"""Frozen legacy API gate."""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def reload_api_main(monkeypatch):
    """Reload api.main after env change."""
    for mod in list(sys.modules):
        if mod == "api.main" or mod.startswith("api.routes") or mod == "api._freeze":
            del sys.modules[mod]
    import api.main as main_mod

    importlib.reload(main_mod)
    return main_mod


def test_api_frozen_by_default(monkeypatch, reload_api_main):
    monkeypatch.delenv("JAVSTORY_ALLOW_FROZEN_API", raising=False)
    app = reload_api_main.app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths
    assert "/api/status" in paths
    assert "/api/library" not in str(paths)
    assert any("/api/harvest" in str(p) for p in paths)


def test_api_legacy_when_env_set(monkeypatch, reload_api_main):
    monkeypatch.setenv("JAVSTORY_ALLOW_FROZEN_API", "1")
    for mod in list(importlib.sys.modules):
        if mod.startswith("api."):
            del importlib.sys.modules[mod]
    import api.main as main_mod

    importlib.reload(main_mod)
    paths = {getattr(r, "path", None) for r in main_mod.app.routes}
    assert any("/api/library" in str(p) for p in paths)
    assert any("/api/harvest" in str(p) for p in paths)
