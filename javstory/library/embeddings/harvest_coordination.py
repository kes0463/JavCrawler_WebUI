"""Coordinate embedding work while Harvest is running."""

from __future__ import annotations

import os
import threading
from typing import Callable, List

_lock = threading.Lock()
_harvest_session_count = 0
_harvest_paused = False
_deferred_codes: set[str] = set()


def embeddings_pause_during_harvest_from_env() -> bool:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST", "1") or "").strip().lower()
    return raw not in ("0", "false", "off", "no")


def harvest_concurrency_from_env() -> int:
    raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
    try:
        n = int(raw) if raw else 2
    except ValueError:
        n = 2
    return max(1, min(5, n))


def is_embedding_harvest_paused() -> bool:
    with _lock:
        return _harvest_paused


def deferred_embedding_count() -> int:
    with _lock:
        return len(_deferred_codes)


def begin_harvest_session(*, logger_func: Callable[[str], None] | None = None) -> None:
    """Increment nested Harvest session count; pause embeddings on first begin."""
    global _harvest_session_count, _harvest_paused
    log = logger_func or (lambda _m: None)
    with _lock:
        _harvest_session_count += 1
        if _harvest_session_count == 1 and embeddings_pause_during_harvest_from_env():
            _harvest_paused = True
            _deferred_codes.clear()
            should_pause = True
        else:
            should_pause = False
    if should_pause:
        log("[Harvest] 임베딩 보류·임베딩용 llama-server 중지 — 크롤링/번역 GPU·RAM 확보")
        _pause_preview_queue()
        _pause_embedding_workers()
        _maybe_stop_embeddings_server(logger_func=log)


def _pause_preview_queue() -> None:
    try:
        from javstory.library.highlight.preview_queue import preview_queue_manager

        preview_queue_manager.pause_for_harvest()
    except Exception:
        pass


def _resume_preview_queue() -> None:
    try:
        from javstory.library.highlight.preview_queue import preview_queue_manager

        preview_queue_manager.resume_after_harvest()
    except Exception:
        pass


def end_harvest_session(*, logger_func: Callable[[str], None] | None = None) -> int:
    """Decrement session count; after last Harvest ends:

    1. Stop translation/chat llama-server (free VRAM/RAM)
    2. Resume embedding/preview workers
    3. Flush deferred product codes into the embedding queue
    4. Start embeddings llama-server (background)
    """
    global _harvest_session_count, _harvest_paused
    log = logger_func or (lambda _m: None)
    codes: List[str] = []
    with _lock:
        if _harvest_session_count > 0:
            _harvest_session_count -= 1
        if _harvest_session_count == 0 and _harvest_paused:
            _harvest_paused = False
            codes = sorted(_deferred_codes)
            _deferred_codes.clear()
            should_resume = True
        else:
            should_resume = False
    if not should_resume:
        return 0

    # Strict sequencing: crawl/translate server off before embeddings server on.
    log("[Harvest] 크롤링 완료 — 번역용 llama-server 종료 후 임베딩으로 전환")
    _maybe_stop_translation_server(logger_func=log)

    n = 0
    if codes:
        n = _flush_deferred_codes(codes, logger_func=log)
        if n:
            log(f"[Harvest] 보류 임베딩 {n}건 큐 등록")

    log("[Harvest] 임베딩·프리뷰 큐 재개")
    _resume_preview_queue()
    _resume_embedding_workers()

    # Start embed server when we flushed deferred work, or queue already has pending jobs.
    if n or _embedding_queue_has_pending():
        _maybe_start_embeddings_server(logger_func=log)
    return n


HARVEST_TUNING_HINTS: list[str] = [
    "JAVSTORY_HARVEST_CONCURRENCY=5 — Harvest 동시 실행 (1~5)",
    "JAVSTORY_LLAMACPP_PARALLEL=5 — llama-server 병렬 슬롯 (env 변경 후 서버 재시작)",
    "JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX=4096 — 슬롯당 ctx (total = slot × parallel, 예: 20480)",
    "JAVSTORY_LLAMACPP_N_GPU_LAYERS=99 + JAVSTORY_LLAMACPP_FIT=off — RAM 오프로드 방지 (Gemma-4-E4B Q4)",
    "JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST=1 — Harvest 중 임베딩 보류; 완료 후 번역 서버 종료→임베딩 서버 기동 (기본 on)",
    "Qwen3-14B + 12GB VRAM: parallel 3 이하 권장; 5병렬은 Gemma-4-E4B 또는 OpenRouter 고려",
]


def harvest_settings_snapshot() -> dict:
    from javstory.llm.llamacpp_backend import (
        describe_llamacpp_spawn_diagnostics,
        harvest_slot_ctx_from_env,
    )

    slot_ctx = harvest_slot_ctx_from_env()
    return {
        "harvest_concurrency": harvest_concurrency_from_env(),
        "embeddings_pause_during_harvest": embeddings_pause_during_harvest_from_env(),
        "harvest_llamacpp_slot_ctx": slot_ctx,
        "llamacpp_spawn_diagnostics": describe_llamacpp_spawn_diagnostics(),
        "tuning_hints": list(HARVEST_TUNING_HINTS),
    }


def defer_product_embedding(product_code: str) -> bool:
    from javstory.persona.library_search import normalize_product_code

    pc = normalize_product_code(product_code)
    if not pc:
        return False
    with _lock:
        _deferred_codes.add(pc)
    return True


def _pause_embedding_workers() -> None:
    try:
        from javstory.library.embeddings.embedding_queue import embedding_queue_manager

        embedding_queue_manager.pause_for_harvest()
    except Exception:
        pass
    try:
        from gui.models.embedding_queue_model import EmbeddingQueueController

        eq = EmbeddingQueueController.instance()
        if eq is not None:
            eq.pause_for_harvest()
    except Exception:
        pass


def _resume_embedding_workers() -> None:
    try:
        from javstory.library.embeddings.embedding_queue import embedding_queue_manager

        embedding_queue_manager.resume_after_harvest()
    except Exception:
        pass
    try:
        from gui.models.embedding_queue_model import EmbeddingQueueController

        eq = EmbeddingQueueController.instance()
        if eq is not None:
            eq.resume_after_harvest()
    except Exception:
        pass


def _maybe_stop_embeddings_server(*, logger_func: Callable[[str], None] | None = None) -> None:
    log = logger_func or (lambda _m: None)
    try:
        from javstory.llm.llamacpp_embeddings import stop_embeddings_llamacpp_server

        stop_embeddings_llamacpp_server(logger_func=log)
    except Exception:
        pass


def _maybe_stop_translation_server(*, logger_func: Callable[[str], None] | None = None) -> None:
    """Stop managed chat/translation llama-server after Harvest completes."""
    log = logger_func or (lambda _m: None)
    try:
        from javstory.llm.llamacpp_backend import (
            persona_chat_uses_managed_llamacpp,
            stop_llamacpp_server,
        )

        if not persona_chat_uses_managed_llamacpp():
            log("[Harvest] 외부 chat URL 사용 중 — 번역용 llama-server 종료 생략")
            return
        stop_llamacpp_server(logger_func=log)
    except Exception as e:
        log(f"[Harvest] 번역용 llama-server 종료 실패: {e}")


def _embedding_queue_has_pending() -> bool:
    try:
        from javstory.library.embeddings.embedding_queue import embedding_queue_manager

        snap = embedding_queue_manager.snapshot()
        if isinstance(snap, dict):
            if int(snap.get("pending_count") or 0) > 0 or int(snap.get("running_count") or 0) > 0:
                return True
            items = snap.get("items")
            if isinstance(items, list):
                return any(
                    isinstance(j, dict) and j.get("status") in ("queued", "running") for j in items
                )
    except Exception:
        pass
    try:
        from gui.models.embedding_queue_model import EmbeddingQueueController

        eq = EmbeddingQueueController.instance()
        if eq is None:
            return False
        if hasattr(eq, "pending_count") and int(getattr(eq, "pending_count") or 0) > 0:
            return True
        if hasattr(eq, "snapshot"):
            snap = eq.snapshot()
            if isinstance(snap, dict):
                if int(snap.get("pending_count") or 0) > 0 or int(snap.get("running_count") or 0) > 0:
                    return True
                items = snap.get("items")
                if isinstance(items, list):
                    return any(
                        isinstance(j, dict) and j.get("status") in ("queued", "running")
                        for j in items
                    )
    except Exception:
        pass
    return False


def _maybe_start_embeddings_server(*, logger_func: Callable[[str], None] | None = None) -> None:
    """Start embeddings backend after Harvest; non-blocking so UI stays responsive."""
    log = logger_func or (lambda _m: None)

    def _run() -> None:
        try:
            from javstory.library.embeddings.pipeline import (
                embeddings_backend_from_env,
                embeddings_enabled_from_env,
            )

            if not embeddings_enabled_from_env():
                return
            if embeddings_backend_from_env() == "ollama":
                from javstory.llm.ollama_serve import ensure_ollama_serve

                ensure_ollama_serve(wait_sec=3.0)
                return
            from javstory.llm.llamacpp_embeddings import ensure_embeddings_llamacpp_ready

            log("[Harvest] 임베딩용 llama-server 기동")
            ensure_embeddings_llamacpp_ready(logger_func=log, wait_sec=90.0)
        except Exception as e:
            log(f"[Harvest] 임베딩용 llama-server 기동 실패: {e}")

    threading.Thread(target=_run, daemon=True, name="HarvestEmbedEnsure").start()


def _flush_deferred_codes(codes: List[str], *, logger_func: Callable[[str], None] | None = None) -> int:
    from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

    if not embeddings_enabled_from_env() or not codes:
        return 0
    n = 0
    for pc in codes:
        if _enqueue_product_embedding_now(pc):
            n += 1
    return n


def _enqueue_product_embedding_now(product_code: str) -> bool:
    from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

    if not embeddings_enabled_from_env():
        return False
    try:
        from gui.models.embedding_queue_model import EmbeddingQueueController

        eq = EmbeddingQueueController.instance()
        if eq is not None:
            eq.enqueue(product_code)
            return True
    except Exception:
        pass
    try:
        from javstory.library.embeddings.embedding_queue import embedding_queue_manager

        return embedding_queue_manager.enqueue(product_code) is not None
    except Exception:
        pass
    try:
        from javstory.library.embeddings.priority_queue import ensure_priority_embeddings_async

        ensure_priority_embeddings_async([product_code], max_batch=1)
        return True
    except Exception:
        return False
