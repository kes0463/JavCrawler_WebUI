"""Shared harvest execution — desktop HarvestWorker parity for WebUI."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ProgressFn = Callable[[str, str, int], None]
LogFn = Callable[[str, str], None]
CancelFn = Callable[[], bool]


@dataclass
class HarvestEntry:
    target: str
    is_path: bool = False
    product_code: str | None = None
    force_rebuild: bool = False

    @classmethod
    def from_tuple(cls, raw: tuple | list) -> HarvestEntry:
        try:
            target = str(raw[0])
            is_path = bool(raw[1]) if len(raw) > 1 else False
            pc = (str(raw[2]).strip() or None) if len(raw) > 2 and raw[2] else None
            force = bool(raw[3]) if len(raw) > 3 else False
            return cls(target=target, is_path=is_path, product_code=pc, force_rebuild=force)
        except Exception:
            return cls(target=str(raw), is_path=False)


def resolve_sku(entry: HarvestEntry) -> str:
    from javstory.utils.product_code import resolve_product_code_for_video

    pc_kw = (entry.product_code or "").strip() or None
    if entry.is_path:
        return resolve_product_code_for_video(entry.target, pc_kw)
    return pc_kw or str(entry.target).strip().upper()


def _default_log(level: str, text: str) -> None:
    print(f"[{level}] {text}", flush=True)


def _translation_queue_available() -> bool:
    """데스크톱 Qt 번역 큐가 살아 있으면 인라인 번역을 생략한다."""
    try:
        from gui.models.translation_queue_model import TranslationQueueController

        return TranslationQueueController.instance() is not None
    except Exception:
        return False


async def run_one(
    entry: HarvestEntry,
    *,
    grok_enabled: bool = False,
    on_progress: ProgressFn | None = None,
    on_log: LogFn | None = None,
    should_cancel: CancelFn | None = None,
) -> dict[str, Any]:
    from javstory.harvest.coordinator import run_crawler_for_video_path
    from javstory.harvest.database import JAVMetadata, assert_db_writable, get_db_session_ctx
    from javstory.harvest.translator import MetadataTranslator

    assert_db_writable("harvest queue")

    log = on_log or _default_log
    prog = on_progress or (lambda _s, _m, _p: None)
    cancelled = should_cancel or (lambda: False)

    sku = resolve_sku(entry)
    item = str(entry.target)
    pc_kw = (entry.product_code or "").strip() or None

    if cancelled():
        return {"ok": False, "sku": sku, "message": "cancelled"}

    log("info", f"[Harvest] {sku} 수집 공정 진입 (Target: {item})")
    prog(sku, "준비 중...", 5)

    if grok_enabled:
        prog(sku, "크롤링·한국어 번역·DB 저장·스토리 맥락(Grok JSON, 캐시)…", 20)
    else:
        prog(sku, "크롤링·한국어 번역·DB 저장…", 20)

    translator = MetadataTranslator()
    inline_translate = not _translation_queue_available()
    try:
        crawler_res = await run_crawler_for_video_path(
            item,
            product_code=pc_kw,
            enable_story_context=False,
            force_rebuild_story_context=bool(entry.force_rebuild),
            skip_translation=not inline_translate,
            skip_media=True,
            translator_instance=translator,
            progress_cb=prog,
        )

        if cancelled():
            return {"ok": False, "sku": sku, "message": "cancelled"}

        if crawler_res.get("error"):
            if crawler_res.get("skeleton_saved"):
                log("warn", f"{sku} 크롤링 실패 — 뼈대 정보 저장됨")
            else:
                err = crawler_res.get("error", "unknown")
                log("error", f"{sku} 수집 실패: {err}")
                return {"ok": False, "sku": sku, "message": f"수집 실패: {err}", "crawler_res": crawler_res}

        prog(sku, "표지 이미지 및 썸네일 생성 중...", 80)

        try:
            with get_db_session_ctx() as session:
                row = session.query(JAVMetadata).filter_by(product_code=sku).first()
                if row:
                    has_local = bool(getattr(row, "cover_image_local_path", None))
                    url = (getattr(row, "cover_image_url", None) or "").strip()
                    is_http = url.startswith("http://") or url.startswith("https://")
                    if (not has_local) and is_http:
                        from javstory.utils.image_handler import ImageHandler

                        img_res = ImageHandler().process_jav_assets(sku, url)
                        if img_res:
                            row.cover_image_local_path = img_res.get("poster_local")
                            row.thumb_image_local_path = img_res.get("thumb_local")
                            from javstory.harvest.database import commit_with_retry

                            commit_with_retry(session)
        except Exception as img_e:
            log("warn", f"[{sku}] 이미지 처리 오류: {img_e}")

        if cancelled():
            return {"ok": False, "sku": sku, "message": "cancelled"}

        prog(sku, "추출 및 최종 정리 중...", 95)
        _enqueue_post_processing(
            sku, item, crawler_res, entry.force_rebuild, log, inline_translate=inline_translate
        )
        prog(sku, "수집 완료 (후처리 큐 등록됨)", 100)
        return {"ok": True, "sku": sku, "message": "기본 수집 성공", "crawler_res": crawler_res}

    except Exception as e:
        log("error", f"[Harvest] {sku} 치명적 에러: {e}")
        return {"ok": False, "sku": sku, "message": str(e)}
    finally:
        try:
            await translator.close()
        except Exception:
            pass


def _enqueue_post_processing(
    sku: str,
    item: str,
    crawler_res: dict[str, Any],
    force_rebuild: bool,
    log: LogFn,
    *,
    inline_translate: bool = False,
) -> None:
    is_skeleton = bool(crawler_res.get("skeleton_saved"))
    try:
        from javstory.harvest.database import JAVMetadata, get_db_session_ctx

        media_video_path: Path | None = None
        direct = Path(item)
        if direct.is_file():
            media_video_path = direct
        else:
            try:
                from gui.library_data import guess_video_path_for_product

                folder_path = None
                with get_db_session_ctx() as session:
                    row = session.query(JAVMetadata).filter_by(product_code=sku).first()
                    if row:
                        folder_path = getattr(row, "folder_path", None)
                guessed = guess_video_path_for_product(sku, folder_path or None)
                if guessed and Path(guessed).is_file():
                    media_video_path = Path(guessed)
            except Exception:
                pass

        if not is_skeleton and not inline_translate:
            try:
                from gui.models.translation_queue_model import TranslationQueueController

                tq = TranslationQueueController.instance()
                if tq:
                    tq.enqueue(sku, item, force_rebuild)
            except Exception:
                pass

        if media_video_path:
            preview_queued = False
            try:
                from gui.models.preview_queue_model import PreviewQueueController

                pq = PreviewQueueController.instance()
                if pq:
                    pq.enqueue(sku, str(media_video_path))
                    preview_queued = True
            except Exception:
                pass
            if not preview_queued:
                try:
                    from javstory.library.highlight.preview_queue import preview_queue_manager

                    preview_queue_manager.push_if_stale(sku, media_video_path)
                except Exception:
                    pass

            try:
                from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT
                from javstory.library.stills.digest_queue import digest_queue_manager
                from javstory.library.stills.snapshot_queue import snapshot_queue_manager

                base_root = Path(E_MEDIA_ROOT)
                if not base_root.exists():
                    base_root = Path(MEDIA_ROOT)
                digest_dir = base_root / sku / "Digest"
                digest_dir.mkdir(parents=True, exist_ok=True)
                digest_queue_manager.push_job(
                    media_video_path, digest_dir / "digest.mp4", product_code=sku
                )
                out_dir = base_root / sku / "Snapshots"
                out_dir.mkdir(parents=True, exist_ok=True)
                snapshot_queue_manager.push_job(media_video_path, out_dir, product_code=sku)
            except Exception as e:
                log("warn", f"미디어 큐 등록 실패: {e}")

        if not is_skeleton:
            try:
                from javstory.library.embeddings.priority_queue import enqueue_product_embedding

                if enqueue_product_embedding(sku):
                    log("info", f"[{sku}] 임베딩 생성 큐 등록")
            except Exception as e:
                log("warn", f"임베딩 큐 등록 실패: {e}")
    except Exception as e:
        log("warn", f"후처리 큐 등록 실패: {e}")


def run_one_sync(
    entry: HarvestEntry,
    *,
    grok_enabled: bool = False,
    on_progress: ProgressFn | None = None,
    on_log: LogFn | None = None,
    should_cancel: CancelFn | None = None,
) -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            run_one(
                entry,
                grok_enabled=grok_enabled,
                on_progress=on_progress,
                on_log=on_log,
                should_cancel=should_cancel,
            )
        )
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
