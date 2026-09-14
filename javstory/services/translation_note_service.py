"""Manual work-translation-note (re)generation for WebUI — mirrors grok_story_service.py."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable

from javstory.persona.library_search import normalize_product_code
from javstory.utils.common import safe_console_print

_LOCK = threading.Lock()
_RUNNING: set[str] = set()


def translation_note_status(product_code: str) -> dict[str, Any]:
    pc = normalize_product_code(product_code)
    if not pc:
        return {"product_code": "", "running": False}
    with _LOCK:
        running = pc in _RUNNING
    return {"product_code": pc, "running": running}


def _resolve_ja_srt_path(product_code: str) -> Path | None:
    """DB의 folder_path → 실제 영상 경로 → 같은 폴더의 .ja.srt/.ja.corrected.srt 순으로 탐색.

    파이프라인 실행 중이 아닐 때(=독립 재생성 버튼)는 이 경로를 아무도 미리 넘겨주지
    않으므로, 라이브러리 상세와 동일한 방식(product_repository/subtitle_parser)으로
    직접 찾는다.
    """
    from javstory.harvest.product_repository import resolve_primary_video_path
    from javstory.library.subtitle_parser import find_subtitle_files
    from javstory.services.library_service import LibraryService

    row = LibraryService().get_by_code(product_code)
    folder_path = getattr(row, "folder_path", None) if row else None
    video_path = resolve_primary_video_path(product_code, folder_path)
    if not video_path:
        return None
    subs = find_subtitle_files(str(video_path))
    by_name = {s["filename"]: s["path"] for s in subs}
    # 교정본이 있으면 우선(더 정확), 없으면 원본 STT 결과.
    for name in (f"{video_path.stem}.ja.corrected.srt", f"{video_path.stem}.ja.srt"):
        if name in by_name:
            return Path(by_name[name])
    return None


async def _run_async(product_code: str, *, use_grok: bool, log: Callable[[str], None]) -> None:
    from javstory.config.secrets_manager import get_openrouter_api_key
    from javstory.llm.engine import MultiTierRouter
    from javstory.translation.story_grok_module import load_cached_grok_json_flexible
    from javstory.translation.subtitle_pipeline_orchestrator import (
        _load_simple_segments_from_srt,
    )
    from javstory.translation.translation_note_generator import (
        ensure_pipeline_work_note_async,
    )

    srt_path = _resolve_ja_srt_path(product_code)
    ja_segments: list[Any] = []
    if srt_path is not None:
        try:
            ja_segments = _load_simple_segments_from_srt(srt_path)
            log(f"JA 자막 로드: {srt_path.name} ({len(ja_segments)}줄)")
        except Exception as e:
            log(f"JA 자막 로드 실패({srt_path}): {e}")
    else:
        log("JA 자막(.ja.srt) 없음 — 제목/시놉시스만으로 생성 시도")

    grok_json: dict[str, Any] | None = None
    if use_grok:
        try:
            grok_json = load_cached_grok_json_flexible(product_code)
        except Exception:
            grok_json = None
        log("Grok 컨텍스트 캐시 참조" if grok_json else "Grok 컨텍스트 캐시 없음 — 미참조로 진행")
    else:
        log("Grok 컨텍스트 미참조(OFF)")

    api_key = (get_openrouter_api_key() or "").strip() or "local"
    router = MultiTierRouter(api_key=api_key, logger_func=log)
    try:
        note = await ensure_pipeline_work_note_async(
            product_code=product_code,
            grok_json=grok_json,
            ja_segments=ja_segments,
            router=router,
            logger_func=log,
            force=True,
        )
        if not note.strip():
            log("생성 결과가 비어 있음 — 자막·메타 정보가 부족할 수 있습니다")
    finally:
        try:
            await router.close()
        except Exception:
            pass


def start_translation_note_generation(
    product_code: str,
    *,
    use_grok: bool = True,
) -> dict[str, Any]:
    """Fire-and-forget 작품 번역 노트 재생성(항상 force). 즉시 반환."""
    pc = normalize_product_code(product_code)
    if not pc:
        return {"ok": False, "queued": 0, "message": "품번이 없습니다."}

    with _LOCK:
        if pc in _RUNNING:
            return {"ok": True, "queued": 0, "message": "이미 생성 중입니다."}
        _RUNNING.add(pc)

    def _worker() -> None:
        def _log(msg: str) -> None:
            safe_console_print(f"[TranslationNote][{pc}] {msg}")

        try:
            asyncio.run(_run_async(pc, use_grok=use_grok, log=_log))
        except Exception as e:
            safe_console_print(f"[TranslationNote][{pc}] failed: {e}")
        finally:
            with _LOCK:
                _RUNNING.discard(pc)

    threading.Thread(target=_worker, daemon=True, name="translation-note-manual").start()
    return {
        "ok": True,
        "queued": 1,
        "message": f"{pc} 작품 번역 노트 재생성을 백그라운드에서 시작합니다.",
    }
