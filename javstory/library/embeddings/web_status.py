"""Embeddings settings / coverage helpers for WebUI."""

from __future__ import annotations

import os
import re
import time
from typing import Any

from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.library.embeddings.pipeline import (
    embeddings_enabled_from_env,
    embeddings_ollama_model_from_env,
)
from javstory.library.embeddings.priority_queue import (
    collect_recommendation_embedding_priorities,
    embeddings_backfill_running,
    ensure_priority_embeddings_async,
    start_embeddings_backfill_async,
)
from javstory.library.embeddings.store import embeddings_cache_dir
from javstory.llm.llamacpp_embeddings import (
    embedding_batch_size,
    embeddings_gguf_scan_dir,
    list_embeddings_gguf_options,
)
from javstory.translation.story_grok_module import story_context_cache_path_grok

_COVERAGE_CACHE: dict[str, Any] = {"at": 0.0, "model": "", "payload": {}}
_COVERAGE_TTL_SEC = 30.0
_LIBRARY_TOTAL_CACHE: dict[str, Any] = {"at": 0.0, "n": 0}
_LIBRARY_TOTAL_TTL_SEC = 300.0


def _library_total_cached() -> int:
    now = time.time()
    cached = _LIBRARY_TOTAL_CACHE
    if (now - float(cached.get("at") or 0.0)) < _LIBRARY_TOTAL_TTL_SEC:
        return int(cached.get("n") or 0)
    n = 0
    try:
        with get_db_session_ctx() as db:
            n = int(db.query(JAVMetadata).count() or 0)
    except Exception:
        n = int(cached.get("n") or 0)
    _LIBRARY_TOTAL_CACHE.update({"at": now, "n": n})
    return n


def embeddings_gguf_options_snapshot() -> dict[str, Any]:
    """GGUF 목록만 — DB·커버리지 없이 빠르게."""
    try:
        options = list_embeddings_gguf_options()
    except Exception:
        options = []
    return {
        "gguf_scan_dir": embeddings_gguf_scan_dir(),
        "gguf_options": options,
    }


def _model_cache_suffix(model: str) -> str:
    m = re.sub(r"[^\w\-.]", "_", (model or "").strip(), flags=re.ASCII) or "model"
    return f"__{m}.json"


def _embedded_mtime_by_code(model: str) -> dict[str, float]:
    """캐시 디렉터리 glob 1회 — DB 전 품번마다 stat 하지 않음."""
    suffix = _model_cache_suffix(model)
    out: dict[str, float] = {}
    try:
        for path in embeddings_cache_dir().glob(f"*{suffix}"):
            if not path.is_file():
                continue
            pc = path.name[: -len(suffix)].strip().upper()
            if not pc:
                continue
            try:
                out[pc] = float(path.stat().st_mtime)
            except OSError:
                out[pc] = 0.0
    except OSError:
        return out
    return out


def _count_pending_stale(*, embedded: dict[str, float]) -> int:
    stale = 0
    for pc, embed_mtime in embedded.items():
        try:
            story_path = story_context_cache_path_grok(pc)
            if story_path.is_file() and story_path.stat().st_mtime > embed_mtime:
                stale += 1
        except OSError:
            continue
    return stale


def _coverage_stats(*, model: str, library_total: int, enabled: bool) -> dict[str, int | float]:
    embedded_map = _embedded_mtime_by_code(model)
    embedded_count = len(embedded_map)
    missing_count = max(0, int(library_total) - embedded_count)
    pending_stale = _count_pending_stale(embedded=embedded_map) if enabled else 0
    pending_count = missing_count + pending_stale
    coverage_pct = round((embedded_count / library_total) * 100.0, 1) if library_total else 0.0
    return {
        "embedded_count": embedded_count,
        "missing_count": missing_count,
        "pending_count": pending_count,
        "coverage_pct": coverage_pct,
    }


def invalidate_embeddings_coverage_cache() -> None:
    _COVERAGE_CACHE["at"] = 0.0


def embeddings_settings_snapshot() -> dict[str, Any]:
    from javstory.library.embeddings.pipeline import embeddings_backend_from_env

    model = embeddings_ollama_model_from_env()
    enabled = embeddings_enabled_from_env()
    backend = embeddings_backend_from_env()
    gguf = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", "") or "").strip()

    library_total = _library_total_cached()

    now = time.time()
    cached = _COVERAGE_CACHE
    if (
        cached.get("model") == model
        and (now - float(cached.get("at") or 0.0)) < _COVERAGE_TTL_SEC
        and isinstance(cached.get("payload"), dict)
    ):
        stats = dict(cached["payload"])
    else:
        stats = _coverage_stats(model=model, library_total=library_total, enabled=enabled)
        _COVERAGE_CACHE.update({"at": now, "model": model, "payload": stats})

    try:
        gguf_options = list_embeddings_gguf_options()
        gguf_scan = embeddings_gguf_scan_dir()
    except Exception:
        gguf_options = []
        gguf_scan = embeddings_gguf_scan_dir()

    return {
        "enabled": enabled,
        "backend": backend,
        "model": model,
        "gguf_path": gguf,
        "gguf_scan_dir": gguf_scan,
        "gguf_options": gguf_options,
        "backfill_running": embeddings_backfill_running(),
        "library_total": library_total,
        "batch_size": embedding_batch_size(),
        **stats,
        **_embedding_search_thresholds(),
    }


def _embedding_search_thresholds() -> dict[str, float]:
    try:
        from javstory.search.library_search import embedding_search_thresholds_from_env

        return embedding_search_thresholds_from_env()
    except Exception:
        return {
            "search_min_score": 0.36,
            "search_relative_ratio": 0.84,
            "search_max_gap": 0.10,
        }


def start_embeddings_warmup(*, max_batch: int = 12) -> dict[str, Any]:
    if not embeddings_enabled_from_env():
        return {
            "ok": False,
            "queued": 0,
            "message": "임베딩이 비활성화되어 있습니다. 먼저 설정에서 켜 주세요.",
        }
    codes = collect_recommendation_embedding_priorities(limit=48)
    model = embeddings_ollama_model_from_env()
    from javstory.library.embeddings.priority_queue import _embedding_needs_build

    pending = [pc for pc in codes if _embedding_needs_build(pc, model=model)]
    batch = max(1, min(24, int(max_batch or 12)))
    ensure_priority_embeddings_async(pending, max_batch=batch)
    queued = min(len(pending), batch)
    if queued <= 0:
        return {
            "ok": True,
            "queued": 0,
            "message": "우선순위 작품의 임베딩이 이미 준비되어 있습니다.",
        }
    from javstory.library.embeddings.pipeline import embeddings_backend_from_env

    backend = embeddings_backend_from_env()
    return {
        "ok": True,
        "queued": queued,
        "message": f"백그라운드에서 {queued}개 작품 임베딩을 생성합니다 ({backend}: {model}).",
    }


def start_embeddings_backfill(*, batch_size: int = 4) -> dict[str, Any]:
    """Queue continuous backfill for all missing / Grok-stale embeddings."""
    if not embeddings_enabled_from_env():
        return {
            "ok": False,
            "queued": 0,
            "message": "임베딩이 비활성화되어 있습니다. 먼저 설정에서 켜 주세요.",
        }
    model = embeddings_ollama_model_from_env()
    already = embeddings_backfill_running()
    pending_n = start_embeddings_backfill_async(batch_size=batch_size)
    invalidate_embeddings_coverage_cache()
    from javstory.library.embeddings.pipeline import embeddings_backend_from_env

    backend = embeddings_backend_from_env()
    if pending_n <= 0:
        return {
            "ok": True,
            "queued": 0,
            "message": "미생성·갱신 대상 임베딩이 없습니다.",
        }
    if already:
        return {
            "ok": True,
            "queued": pending_n,
            "message": f"이미 백필이 진행 중입니다. 남은 대상 약 {pending_n}건 ({backend}: {model}).",
        }
    return {
        "ok": True,
        "queued": pending_n,
        "message": f"미생성·Grok 갱신 대상 {pending_n}건 임베딩 백필을 시작합니다 ({backend}: {model}).",
    }
