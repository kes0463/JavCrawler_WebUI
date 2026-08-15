"""
Embedding pipeline:
- Build docs (meta + canonical + subtitles)
- Embed with llama-server (default) or Ollama
- Persist to data/cache/embeddings
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from javstory.library.canonical.schema import LibraryCanonical
from javstory.library.detail_persist import apply_jav_metadata_row_to_canonical_meta, load_canonical_for_product
from javstory.library.embeddings.document_builder import build_embedding_documents
from javstory.library.embeddings.store import embeddings_cache_path, write_embeddings_json
from javstory.llm.llamacpp_embeddings import embeddings_model_from_env as _llamacpp_model_from_env
from javstory.translation.story_grok_module import story_context_cache_path_grok


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def embeddings_enabled_from_env() -> bool:
    v = (os.environ.get("JAVSTORY_EMBEDDINGS_ENABLED", "") or "").strip().lower()
    if not v:
        return False
    return v in ("1", "true", "yes", "on")


def embeddings_backend_from_env() -> str:
    """llamacpp (기본) | ollama."""
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_BACKEND", "") or "").strip().lower()
    if raw in ("ollama", "o"):
        return "ollama"
    if raw in ("llamacpp", "llama", "llama.cpp", "llama-server", "gguf"):
        return "llamacpp"
    # 미설정 → llama-server
    return "llamacpp"


def embeddings_model_from_env() -> str:
    return _llamacpp_model_from_env()


def embeddings_ollama_model_from_env() -> str:
    """하위 호환 별칭 — 실제로는 embeddings_model_from_env 와 동일."""
    return embeddings_model_from_env()


def _story_context_newer_than_embedding(product_code: str, embedding_path: Path) -> bool:
    if not embedding_path.is_file():
        return False
    try:
        story_path = story_context_cache_path_grok(product_code)
        if not story_path.is_file():
            return False
        return story_path.stat().st_mtime > embedding_path.stat().st_mtime
    except OSError:
        return False


def _canonical_needs_db_enrich(state: LibraryCanonical) -> bool:
    return not any(
        str(getattr(state, field, "") or "").strip()
        for field in ("title_ko", "title_ja", "actress", "synopsis_short", "overall_summary")
    )


def _enrich_canonical_from_db(state: LibraryCanonical, product_code: str) -> LibraryCanonical:
    if not _canonical_needs_db_enrich(state):
        return state
    try:
        from javstory.harvest.database import JAVMetadata, get_db_session_ctx

        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=product_code).first()
            if row:
                return apply_jav_metadata_row_to_canonical_meta(state, row)
    except Exception:
        pass
    return state


async def _embed_texts(texts: List[str], *, model: str, logger_func: Any = None) -> List[List[float]]:
    import asyncio

    log = logger_func or (lambda *_a, **_k: None)
    backend = embeddings_backend_from_env()
    if backend == "ollama":
        from javstory.llm.engine import ollama_ensure_model
        from javstory.llm.ollama_embeddings import ollama_embed_texts

        log(f"🔢 임베딩 백엔드: Ollama ({model})")
        await ollama_ensure_model(model, logger_func=log)
        return await ollama_embed_texts(texts=texts, model=model)

    from javstory.llm.llamacpp_embeddings import (
        ensure_embeddings_llamacpp_ready,
        llamacpp_embed_texts,
    )

    log(f"🔢 임베딩 백엔드: llama-server ({model})")
    await asyncio.to_thread(ensure_embeddings_llamacpp_ready, logger_func=log)
    return await llamacpp_embed_texts(texts=texts, model=model)


async def embed_texts(
    texts: List[str],
    *,
    model: str | None = None,
    logger_func: Any = None,
) -> List[List[float]]:
    """백엔드(llama-server/Ollama)에 맞춰 텍스트 임베딩."""
    m = (model or "").strip() or embeddings_model_from_env()
    return await _embed_texts(texts, model=m, logger_func=logger_func)


async def build_and_store_embeddings_for_product(
    product_code: str,
    *,
    state: LibraryCanonical | None = None,
    model: str | None = None,
    include_subtitles: bool = True,
    force: bool = False,
    logger_func: Any = None,
) -> Path | None:
    """
    Returns path if written, else None (skipped).
    """
    log = logger_func or (lambda *_a, **_k: None)
    pc = (product_code or "").strip().upper()
    if not pc:
        return None

    m = (model or "").strip() or embeddings_model_from_env()
    out_path = embeddings_cache_path(pc, model=m)

    if out_path.is_file() and not force:
        if not _story_context_newer_than_embedding(pc, out_path):
            log(f"✅ 임베딩 캐시 이미 존재: {out_path.name}")
            return out_path
        log("♻️ 스토리 컨텍스트가 임베딩보다 최신입니다. 임베딩을 재생성합니다.")

    st = state if state is not None else load_canonical_for_product(pc)
    st = _enrich_canonical_from_db(st, pc)

    subtitles_max_chars = 200_000
    if embeddings_backend_from_env() == "llamacpp":
        from javstory.llm.llamacpp_embeddings import embedding_max_input_chars

        subtitles_max_chars = embedding_max_input_chars()

    docs = build_embedding_documents(
        st,
        include_subtitles=include_subtitles,
        subtitles_max_chars=subtitles_max_chars,
    )
    if embeddings_backend_from_env() == "llamacpp":
        from javstory.llm.llamacpp_embeddings import truncate_embedding_input

        for doc in docs:
            doc["text"] = truncate_embedding_input(str(doc.get("text") or ""))
    if not docs:
        log("⚠️ 임베딩 스킵: 문서가 비어 있습니다.")
        return None

    vectors = await _embed_texts([d["text"] for d in docs], model=m, logger_func=log)

    payload: Dict[str, Any] = {
        "product_code": pc,
        "model": m,
        "backend": embeddings_backend_from_env(),
        "generated_at": _utc_now_iso(),
        "docs": [
            {
                "doc_id": d.get("doc_id"),
                "kind": d.get("kind"),
                "text": d.get("text"),
                "meta": d.get("meta") or {},
                "embedding": v,
            }
            for d, v in zip(docs, vectors)
        ],
    }

    write_embeddings_json(out_path, payload, indent=2)
    log(f"✅ 임베딩 저장 완료: {out_path}")
    return out_path


__all__ = [
    "embeddings_enabled_from_env",
    "embeddings_backend_from_env",
    "embeddings_model_from_env",
    "embeddings_ollama_model_from_env",
    "embed_texts",
    "build_and_store_embeddings_for_product",
]
