"""JAVSTORY FastAPI — frozen legacy stack (non-production).

운영 UI: main.py + QML. See docs/adr/0001-ui-stack-qml-only.md.

기본: /health, /api/status 만 노출.
레거시 라우트: JAVSTORY_ALLOW_FROZEN_API=1 일 때만 library + harvest 마운트.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api._freeze import (
    ENV_ALLOW_FROZEN_API,
    FROZEN_DETAIL,
    FROZEN_MESSAGE,
    allow_frozen_api,
)

_LEGACY = allow_frozen_api()

app = FastAPI(
    title="JAVSTORY API (frozen legacy)",
    version="1.0.0",
    description=FROZEN_MESSAGE,
)

_cors_env = os.environ.get("JAVSTORY_CORS_ORIGINS", "").strip()
_CORS_ORIGINS: list[str] = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "null",
    ]
)

if _LEGACY:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "api_mode": "legacy_enabled" if _LEGACY else "frozen",
        "frozen": not _LEGACY,
    }


@app.get("/api/status")
def api_status():
    """동결 상태·레거시 활성화 방법."""
    out = dict(FROZEN_DETAIL)
    out["legacy_routes_mounted"] = _LEGACY
    if _LEGACY:
        out["library_prefix"] = "/api/library"
        out["harvest_prefix"] = "/api/harvest"
    return out


if _LEGACY:
    from api.routes import harvest, library

    app.include_router(library.router, prefix="/api/library", tags=["library"])
    app.include_router(harvest.router, prefix="/api/harvest", tags=["harvest"])
    print(
        f"[API] WARNING: legacy routes enabled ({ENV_ALLOW_FROZEN_API}=1). "
        "Unsupported — use main.py for production."
    )
else:
    from api.routes import harvest_frozen

    app.include_router(
        harvest_frozen.router,
        prefix="/api/harvest",
        tags=["harvest-frozen"],
    )
    print(f"[API] Frozen — only /health and /api/status. Set {ENV_ALLOW_FROZEN_API}=1 for legacy.")


def main() -> None:
    """python -m api.main — frozen 시 종료."""
    if not _LEGACY:
        print(FROZEN_MESSAGE)
        print(f"To run legacy API: set {ENV_ALLOW_FROZEN_API}=1")
        raise SystemExit(2)
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("JAVSTORY_API_PORT", "8765")),
        reload=False,
    )


if __name__ == "__main__":
    main()
