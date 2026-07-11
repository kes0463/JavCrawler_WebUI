"""Manual / batch Grok story-context generation for WebUI."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from javstory.persona.library_search import normalize_product_code
from javstory.translation.story_grok_module import (
    has_disk_grok_story_cache,
    run_story_grok_after_harvest_async,
    story_context_cache_path_grok,
)

_LOCK = threading.Lock()
_RUNNING: set[str] = set()


def grok_story_status(product_code: str) -> dict[str, Any]:
    pc = normalize_product_code(product_code)
    if not pc:
        return {"product_code": "", "has_cache": False, "running": False, "path": None}
    path = story_context_cache_path_grok(pc)
    with _LOCK:
        running = pc in _RUNNING
    return {
        "product_code": pc,
        "has_cache": bool(has_disk_grok_story_cache(pc)),
        "running": running,
        "path": str(path) if path.is_file() else None,
    }


def start_grok_story_generation(
    product_codes: list[str],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Fire-and-forget Grok story context generation for one or more products.

    Returns immediately with how many jobs were accepted.
    """
    codes: list[str] = []
    seen: set[str] = set()
    for raw in product_codes or []:
        pc = normalize_product_code(str(raw or ""))
        if not pc or pc in seen:
            continue
        seen.add(pc)
        codes.append(pc)

    if not codes:
        return {"ok": False, "queued": 0, "skipped": 0, "message": "품번이 없습니다."}

    accepted: list[str] = []
    skipped = 0
    with _LOCK:
        for pc in codes:
            if pc in _RUNNING:
                skipped += 1
                continue
            if not force and has_disk_grok_story_cache(pc):
                skipped += 1
                continue
            _RUNNING.add(pc)
            accepted.append(pc)

    if not accepted:
        return {
            "ok": True,
            "queued": 0,
            "skipped": skipped,
            "message": (
                "이미 캐시가 있거나 생성 중입니다. 강제 재생성하려면 force=true를 사용하세요."
                if skipped
                else "대기열이 비어 있습니다."
            ),
        }

    def _worker(batch: list[str]) -> None:
        from javstory.config.app_config import library_story_context_batch_tier

        tier = library_story_context_batch_tier()
        for pc in batch:
            try:

                def _log(msg: str, _pc: str = pc) -> None:
                    print(f"[GrokStory][{_pc}] {msg}")

                asyncio.run(
                    run_story_grok_after_harvest_async(
                        product_code=pc,
                        logger_func=_log,
                        story_context_tier=tier,
                        force_refresh=bool(force),
                    )
                )
            except Exception as e:
                print(f"[GrokStory][{pc}] failed: {e}")
            finally:
                with _LOCK:
                    _RUNNING.discard(pc)

    threading.Thread(
        target=_worker,
        args=(accepted,),
        daemon=True,
        name="grok-story-manual",
    ).start()

    verb = "재생성" if force else "생성"
    return {
        "ok": True,
        "queued": len(accepted),
        "skipped": skipped,
        "message": f"Grok 스토리 컨텍스트 {verb} {len(accepted)}건을 백그라운드에서 시작합니다.",
    }
