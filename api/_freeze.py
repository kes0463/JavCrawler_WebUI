"""Frozen API gate — legacy `api/` + `frontend/` only when explicitly opted in."""

from __future__ import annotations

import os

ENV_ALLOW_FROZEN_API = "JAVSTORY_ALLOW_FROZEN_API"

FROZEN_MESSAGE = (
    "api/ is frozen (non-production). Use main.py + QML. "
    "See docs/adr/0001-ui-stack-qml-only.md"
)

FROZEN_DETAIL: dict[str, object] = {
    "frozen": True,
    "message": FROZEN_MESSAGE,
    "enable_env": ENV_ALLOW_FROZEN_API,
    "adr": "docs/adr/0001-ui-stack-qml-only.md",
    "production_entry": "main.py",
}


def allow_frozen_api() -> bool:
    v = os.getenv(ENV_ALLOW_FROZEN_API, "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def frozen_http_exception() -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=410, detail=FROZEN_DETAIL)
