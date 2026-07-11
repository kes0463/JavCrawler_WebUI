"""Embeddings settings / coverage helpers for WebUI."""

from __future__ import annotations

from typing import Any

from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.library.embeddings.pipeline import (
    embeddings_enabled_from_env,
    embeddings_ollama_model_from_env,
)
from javstory.library.embeddings.priority_queue import (
    collect_recommendation_embedding_priorities,
    ensure_priority_embeddings_async,
    _embedding_needs_build,
)
from javstory.library.embeddings.store import embeddings_cache_path


def embeddings_settings_snapshot() -> dict[str, Any]:
    model = embeddings_ollama_model_from_env()
    enabled = embeddings_enabled_from_env()
    embedded = 0

    try:
        with get_db_session_ctx() as db:
            library_total = int(db.query(JAVMetadata).count() or 0)
            codes = [
                str(r[0] or "").strip().upper()
                for r in db.query(JAVMetadata.product_code).all()
                if str(r[0] or "").strip()
            ]
    except Exception:
        library_total = 0
        codes = []

    for pc in codes:
        try:
            if embeddings_cache_path(pc, model=model).is_file():
                embedded += 1
        except Exception:
            continue

    missing = max(0, library_total - embedded)
    coverage = round((embedded / library_total) * 100.0, 1) if library_total else 0.0
    return {
        "enabled": enabled,
        "model": model,
        "embedded_count": embedded,
        "library_total": library_total,
        "missing_count": missing,
        "coverage_pct": coverage,
    }


def start_embeddings_warmup(*, max_batch: int = 12) -> dict[str, Any]:
    if not embeddings_enabled_from_env():
        return {
            "ok": False,
            "queued": 0,
            "message": "임베딩이 비활성화되어 있습니다. 먼저 설정을 켜 주세요.",
        }
    codes = collect_recommendation_embedding_priorities(limit=48)
    model = embeddings_ollama_model_from_env()
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
    return {
        "ok": True,
        "queued": queued,
        "message": f"백그라운드에서 {queued}개 작품 임베딩을 생성합니다 (Ollama: {model}).",
    }
