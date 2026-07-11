from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.config.app_config import ensure_project_env_loaded

ensure_project_env_loaded()

from javstory.utils.ffmpeg_path import bootstrap_path_env

bootstrap_path_env()

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webapi.routes import actress, dashboard, folder_watch, harvest, insight, library, playback, processing, settings
from webapi.routes.harvest import bind_harvest_broadcast
from webapi.routes.processing import bind_processing_broadcast


@asynccontextmanager
async def lifespan(app: FastAPI):
    from javstory.harvest.database import _run_idempotent_column_migrations

    try:
        from anyio import to_thread

        limiter = to_thread.current_default_thread_limiter()
        limiter.total_tokens = max(limiter.total_tokens, 64)
    except Exception:
        pass

    _run_idempotent_column_migrations()
    bind_harvest_broadcast(asyncio.get_running_loop())
    bind_processing_broadcast(asyncio.get_running_loop())

    def _preview_stale_backfill() -> None:
        if (os.environ.get("JAVSTORY_PREVIEW_BACKFILL_ON_START", "1") or "").strip().lower() in {
            "0",
            "false",
            "off",
            "no",
        }:
            return
        try:
            from javstory.library.highlight.preview_queue import preview_queue_manager

            preview_queue_manager.enqueue_stale_from_db()
        except Exception:
            pass

    import threading

    threading.Thread(target=_preview_stale_backfill, daemon=True, name="PreviewStaleBackfill").start()

    try:
        from javstory.folder_watch.service import get_folder_watch_service

        get_folder_watch_service().start()
    except Exception:
        pass

    yield


app = FastAPI(
    title="JAVSTORY WebAPI",
    version="1.0.0",
    description="Production HTTP API for React WebUI",
    lifespan=lifespan,
)

_cors_env = os.environ.get("JAVSTORY_CORS_ORIGINS", "").strip()
_CORS_ORIGINS: list[str] = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else [
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "HEAD", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Range"],
    expose_headers=["Accept-Ranges", "Content-Length", "Content-Range"],
)

app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(actress.router, prefix="/api/actresses", tags=["actresses"])
app.include_router(playback.router, prefix="/api/playback", tags=["playback"])
app.include_router(harvest.router, prefix="/api/harvest", tags=["harvest"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(folder_watch.router, prefix="/api/folder-watch", tags=["folder-watch"])
app.include_router(insight.router, prefix="/api/insight", tags=["insight"])
app.include_router(processing.router, prefix="/api/processing", tags=["processing"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])


@app.get("/health")
def health():
    return {"status": "ok", "api": "webapi"}


@app.get("/api/status")
def api_status():
    from javstory.config.app_config import DB_PATH, E_DATA_ROOT
    from javstory.harvest.database import get_db_session_ctx, Actress

    actress_count = 0
    try:
        with get_db_session_ctx() as session:
            actress_count = session.query(Actress).count()
    except Exception:
        pass
    return {
        "api": "webapi",
        "version": "1.0.0",
        "db_path": str(DB_PATH),
        "e_data_root": str(E_DATA_ROOT),
        "actress_count": actress_count,
        "library_prefix": "/api/library",
        "library_patch": True,
        "library_genres": True,
        "actresses_prefix": "/api/actresses",
        "harvest_prefix": "/api/harvest",
        "dashboard_prefix": "/api/dashboard",
    }


def main() -> None:
    import uvicorn

    uvicorn.run(
        "webapi.main:app",
        host=os.environ.get("JAVSTORY_WEBAPI_HOST", "127.0.0.1"),
        port=int(os.environ.get("JAVSTORY_WEBAPI_PORT", "8765")),
        reload=False,
    )


if __name__ == "__main__":
    main()
