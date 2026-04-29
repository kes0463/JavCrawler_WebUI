"""
KO 자막 번역(Ollama) VRAM: N작품마다만 언로드, 그 사이에는 VRAM 유지(번역은 순차 1작품씩).
환경: JAVSTORY_TRANSLATION_OLLAMA_VRAM_BATCH (기본 50, 최소 1)
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

_lock = threading.Lock()
_loaded_model: Optional[str] = None
_works_since_load: int = 0  # 이번 VRAM 유지 구간에서 완료한 작품 수(한 작품 = translate_ja_segments_to_ko_async 1회)


def ollama_vram_works_per_batch() -> int:
    raw = (os.environ.get("JAVSTORY_TRANSLATION_OLLAMA_VRAM_BATCH", "") or "").strip()
    try:
        n = int(raw) if raw else 50
    except ValueError:
        n = 50
    return max(1, n)


def reset_session() -> None:
    """테스트·외부 비우기 감지 시: 세션 초기화(다음 작품에서 ensure)."""
    global _loaded_model, _works_since_load
    with _lock:
        _loaded_model = None
        _works_since_load = 0


async def before_ko_translate_work(model: str, logger_func: Any = None) -> None:
    from javstory.llm.engine import ollama_ensure_model, ollama_unload_model

    log = logger_func or print
    global _loaded_model, _works_since_load
    m = (model or "").strip()
    if not m:
        return

    unload_old: Optional[str] = None
    with _lock:
        if _loaded_model is not None and _loaded_model != m:
            unload_old = _loaded_model

    if unload_old is not None:
        await ollama_unload_model(unload_old, logger_func=log)
        with _lock:
            if _loaded_model == unload_old:
                _loaded_model = None
                _works_since_load = 0

    with _lock:
        need_ensure = _loaded_model is None
    if need_ensure:
        await ollama_ensure_model(m, logger_func=log)
        with _lock:
            _loaded_model = m
        b = ollama_vram_works_per_batch()
        log(
            f"[Ollama VRAM] ensure 완료 — {b}작마다 1회 언로드, 그 사이 VRAM 유지(순차 1작품/번)"
        )


async def after_ko_translate_work(model: str, logger_func: Any = None) -> None:
    from javstory.llm.engine import ollama_unload_model

    log = logger_func or print
    global _works_since_load, _loaded_model
    m = (model or "").strip()
    if not m:
        return

    batch = ollama_vram_works_per_batch()
    to_unload = False
    with _lock:
        if _loaded_model is None and _works_since_load == 0:
            return
        _works_since_load += 1
        w = _works_since_load
        if _loaded_model is None or _loaded_model != m or w < batch:
            return
        # w == batch, 모델 일치: 언로드 후 배치 경계
        to_unload = True
        _works_since_load = 0
        _loaded_model = None

    if to_unload:
        await ollama_unload_model(m, logger_func=log)
        if log:
            log(f"[Ollama VRAM] {batch}작 누적 — 언로드(다음 작부터 VRAM 다시 올림)")

