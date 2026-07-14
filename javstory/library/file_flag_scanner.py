"""작품 파일 상태 스캔 → file_flag_cache 갱신.

row_to_summary_fast()가 매번 수행하던 HDD I/O(작품당 10~15회)를
백그라운드에서 한 번만 수행하고 DB에 캐시해 라이브러리 로딩 속도를 개선한다.
"""

from __future__ import annotations

import datetime
import sqlite3
import threading
from pathlib import Path
from typing import Callable

_LAMP_SUB_REPAIR_DONE = False
_LAMP_STT_REPAIR_DONE = False
_LAMP_REPAIR_LOCK = threading.Lock()
_LAMP_REPAIR_THREAD: threading.Thread | None = None
_LAMP_REPAIR_PENDING_SUB = False
_LAMP_REPAIR_PENDING_STT = False


def _now_iso() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def resolve_preview_path(product_code: str) -> str | None:
    """그리드용 preview.webp 경로. 없으면 None."""
    return _resolve_preview_path(product_code)


def _resolve_preview_path(product_code: str) -> str | None:
    """그리드용 preview.webp 경로 해석(base 품번 기준). 없으면 None.

    gui 레이어에 의존하지 않도록 경로 규칙을 인라인한다
    (gui.models.library.search.preview_path_for 와 동일 규칙).
    """
    try:
        from javstory.config.app_config import DATA_ROOT, E_MEDIA_ROOT
        from javstory.utils.product_code import strip_split_suffixes
    except Exception:
        return None

    code = (product_code or "").strip().upper()
    if not code:
        return None
    try:
        base = strip_split_suffixes(code) or code
    except Exception:
        base = code

    cands = [
        Path(E_MEDIA_ROOT) / base / "Preview" / "preview.webp",
        Path(DATA_ROOT) / "media" / base / "Preview" / "preview.webp",
    ]
    for p in cands:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return str(p.resolve())
            mp4 = p.with_suffix(".mp4")
            if mp4.is_file() and mp4.stat().st_size > 0:
                return str(p.resolve())
        except Exception:
            continue
    return None


def _is_subtitle_srt_name(name: str) -> bool:
    n = (name or "").lower()
    return n.endswith(".ko.srt") or (n.endswith(".srt") and not n.endswith(".ja.srt"))


def _sidecar_has_ko_or_plain(video_path: Path) -> bool:
    stem = str(video_path.with_suffix(""))
    # video.is_file() 선행 검사 금지 — 오프라인/느린 드라이브에서 이중 stat
    return Path(stem + ".ko.srt").is_file() or Path(stem + ".srt").is_file()


def _sidecar_has_ja(video_path: Path) -> bool:
    stem = str(video_path.with_suffix(""))
    return Path(stem + ".ja.srt").is_file()


def _folder_contains_subtitle_srt(
    folder_path: str | None,
    product_code: str = "",
    video_path: Path | None = None,
) -> bool:
    """영상 옆 사이드카 또는 폴더 내 KO/일반 SRT 존재 여부."""
    vp = video_path
    if vp is None or not vp.is_file():
        fp = (folder_path or "").strip()
        if fp and product_code:
            try:
                from javstory.library.video_discovery import guess_video_path_for_product_fast

                vp = guess_video_path_for_product_fast(product_code, fp)
            except Exception:
                vp = None
    if vp and vp.is_file() and _sidecar_has_ko_or_plain(vp):
        return True
    root = Path((folder_path or "").strip())
    if not root.is_dir():
        return False
    try:
        for p in root.rglob("*"):
            if p.is_file() and _is_subtitle_srt_name(p.name):
                return True
    except OSError:
        pass
    return False


def scan_one(product_code: str, folder_path: str | None, is_hardcoded: bool = False) -> dict:
    """작품 1개의 파일 상태를 스캔해 dict 반환 (스레드 안전)."""
    from javstory.library.video_discovery import guess_video_path_for_product_fast
    from javstory.library.paths import library_state_path

    pc = (product_code or "").strip().upper()

    has_canonical = library_state_path(pc).is_file() if pc else False

    vp: Path | None = None
    if folder_path:
        try:
            vp = guess_video_path_for_product_fast(pc, folder_path)
        except Exception:
            vp = None

    has_video = vp is not None

    lamp_stt = False
    lamp_sub = False
    if not is_hardcoded:
        if vp:
            stem = str(vp.with_suffix(""))
            ja = Path(stem + ".ja.srt").is_file()
            ko = Path(stem + ".ko.srt").is_file()
            pl = Path(stem + ".srt").is_file()
            if ja or ko or pl:
                # 사이드카 파일 규칙: .ja.srt → STT 완료, .ko.srt/.srt → 자막 완료
                lamp_stt = ja
                lamp_sub = ko or pl
            else:
                # 사이드카 없으면 파이프라인 산출물 경로 체크
                try:
                    from javstory.pipeline.orchestrator import get_pipeline_status
                    st = get_pipeline_status(product_code=pc, video_path=vp, harvest_ok=True)
                    lamp_stt = bool(st.ja_srt_exists)
                    lamp_sub = bool(st.ko_srt_exists or st.srt_fallback_exists)
                except Exception:
                    pass
        else:
            # 폴더 미연결: 파이프라인 산출물 캐시만 확인
            try:
                from javstory.pipeline.orchestrator import get_pipeline_status
                st = get_pipeline_status(product_code=pc, video_path=None, harvest_ok=True)
                lamp_stt = bool(st.ja_srt_exists)
                lamp_sub = bool(st.ko_srt_exists or st.srt_fallback_exists)
            except Exception:
                pass
        # 사이드카/파이프라인에 없어도 폴더 안에 KO·일반 SRT가 있으면 자막 있음
        if not lamp_sub and folder_path:
            if _folder_contains_subtitle_srt(folder_path, pc, vp):
                lamp_sub = True

    has_story = False
    try:
        from javstory.translation.story_grok_module import has_disk_grok_story_cache
        has_story = bool(has_disk_grok_story_cache(pc))
    except Exception:
        pass

    cover_path: str | None = None
    try:
        from javstory.library.cover_cache import resolve_cover_path
        eff = resolve_cover_path(pc)
        cover_path = str(eff) if eff else None
    except Exception:
        cover_path = None

    preview_path = _resolve_preview_path(pc)

    return {
        "product_code": pc,
        "has_video": int(has_video),
        "video_path": str(vp) if vp else None,
        "lamp_stt": int(lamp_stt),
        "lamp_sub": int(lamp_sub),
        "has_canonical": int(has_canonical),
        "has_story": int(has_story),
        "cover_path": cover_path,
        "preview_path": preview_path,
        "scanned_at": _now_iso(),
    }


def _bulk_upsert(db_path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO file_flag_cache
               (product_code, has_video, video_path, lamp_stt, lamp_sub,
                has_canonical, has_story, cover_path, preview_path, scanned_at)
               VALUES (:product_code, :has_video, :video_path, :lamp_stt, :lamp_sub,
                       :has_canonical, :has_story, :cover_path, :preview_path, :scanned_at)""",
            rows,
        )
        conn.commit()


def bulk_scan_and_save(
    items: list[tuple[str, str | None, bool]],
    *,
    on_progress: Callable[[int, int], None] | None = None,
    batch_size: int = 200,
) -> int:
    """
    (product_code, folder_path, is_hardcoded) 목록을 병렬 스캔하고 DB에 일괄 저장.

    ThreadPoolExecutor(max_workers=4)로 3개 HDD를 동시에 읽어 속도를 높인다.
    반환값: 저장된 건수.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from javstory.harvest.database import DB_PATH

    total = len(items)
    if not total:
        return 0

    results: list[dict] = []
    done = 0

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(scan_one, pc, fp, hc): i for i, (pc, fp, hc) in enumerate(items)}
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception:
                pass
            done += 1
            if on_progress:
                try:
                    on_progress(done, total)
                except Exception:
                    pass

            # 배치 단위로 DB에 저장해 메모리 누적 방지
            if len(results) >= batch_size:
                _bulk_upsert(DB_PATH, results)
                results.clear()

    if results:
        _bulk_upsert(DB_PATH, results)

    return done


def load_all_flags_as_dict(session) -> dict[str, dict]:
    """file_flag_cache 전체를 {product_code: flags_dict}로 반환 (단일 쿼리)."""
    from javstory.harvest.database import FileFlagCache

    rows = session.query(FileFlagCache).all()
    return {
        r.product_code: {
            "has_video": r.has_video,
            "video_path": r.video_path,
            "lamp_stt": r.lamp_stt,
            "lamp_sub": r.lamp_sub,
            "has_canonical": r.has_canonical,
            "has_story": r.has_story,
            "cover_path": getattr(r, "cover_path", None),
            "preview_path": getattr(r, "preview_path", None),
        }
        for r in rows
    }


def load_flags_for_codes(session, product_codes: list[str]) -> dict[str, dict]:
    """지정 품번 목록의 파일 플래그를 {product_code: flags_dict}로 반환."""
    from javstory.harvest.database import FileFlagCache

    if not product_codes:
        return {}
    rows = session.query(FileFlagCache).filter(
        FileFlagCache.product_code.in_(product_codes)
    ).all()
    return {
        r.product_code: {
            "has_video": r.has_video,
            "video_path": r.video_path,
            "lamp_stt": r.lamp_stt,
            "lamp_sub": r.lamp_sub,
            "has_canonical": r.has_canonical,
            "has_story": r.has_story,
            "cover_path": getattr(r, "cover_path", None),
            "preview_path": getattr(r, "preview_path", None),
        }
        for r in rows
    }


def upsert_one_flag(product_code: str, folder_path: str | None, is_hardcoded: bool = False) -> None:
    """단일 작품 파일 상태를 스캔해 DB 즉시 갱신 (하베스트·FolderWatch 완료 시 호출)."""
    from javstory.harvest.database import DB_PATH

    row = scan_one(product_code, folder_path, is_hardcoded)
    _bulk_upsert(DB_PATH, [row])


def refresh_flags_after_media_change(
    product_code: str,
    video_path: str | Path | None = None,
) -> None:
    """STT/자막 생성 후 lamp_stt·lamp_sub 등 파일 플래그 캐시를 즉시 갱신."""
    pc = (product_code or "").strip().upper()
    vp: Path | None = None
    if video_path:
        try:
            vp = Path(video_path)
        except Exception:
            vp = None
    if not pc and vp is not None:
        try:
            from javstory.utils.product_code import resolve_product_code_for_video

            pc = (resolve_product_code_for_video(vp) or "").strip().upper()
        except Exception:
            pc = ""
    if not pc:
        return

    folder: str | None = None
    is_hardcoded = False
    try:
        from javstory.harvest.database import get_db_session, JAVMetadata

        session = get_db_session()
        try:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row:
                folder = (getattr(row, "folder_path", None) or "").strip() or None
                is_hardcoded = bool(getattr(row, "is_hardcoded", False))
        finally:
            session.close()
    except Exception:
        pass
    if not folder and vp is not None:
        try:
            folder = str(vp.parent)
        except Exception:
            folder = None
    upsert_one_flag(pc, folder, is_hardcoded)
    invalidate_lamp_flag_repair_cache()


def repair_stale_lamp_sub_flags(*, force: bool = False) -> dict[str, int]:
    """lamp_sub=0 인데 영상 옆 KO/일반 SRT가 있으면 lamp_sub=1로 고친다.

    자막 필터(SQL)가 오래된 캐시 때문에 '자막 없음'에 잘못 넣는 문제를 막는다.
    기본은 프로세스당 1회만 실행(force=True로 재실행).
    폴더 전체 iterdir는 하지 않는다(느린 HDD/네트워크에서 필터 지연 원인).
    """
    global _LAMP_SUB_REPAIR_DONE
    if _LAMP_SUB_REPAIR_DONE and not force:
        return {"checked": 0, "updated": 0, "skipped": 1}

    from sqlalchemy import or_

    from javstory.harvest.database import FileFlagCache, JAVMetadata, get_db_session

    checked = 0
    updated = 0
    session = get_db_session()
    try:
        rows = (
            session.query(FileFlagCache, JAVMetadata)
            .outerjoin(
                JAVMetadata,
                FileFlagCache.product_code == JAVMetadata.product_code,
            )
            .filter(or_(FileFlagCache.lamp_sub == 0, FileFlagCache.lamp_sub.is_(None)))
            .all()
        )
        for cache, meta in rows:
            checked += 1
            if meta is not None and bool(getattr(meta, "is_hardcoded", False)):
                continue
            if not cache.video_path:
                continue
            try:
                vp = Path(cache.video_path)
            except Exception:
                continue
            if _sidecar_has_ko_or_plain(vp):
                cache.lamp_sub = 1
                updated += 1
        if updated:
            session.commit()
        else:
            session.rollback()
        _LAMP_SUB_REPAIR_DONE = True
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()
    return {"checked": checked, "updated": updated, "skipped": 0}


def repair_stale_lamp_stt_flags(*, force: bool = False) -> dict[str, int]:
    """lamp_stt=0 인데 영상 옆 .ja.srt가 있으면 lamp_stt=1로 고친다.

    일본어 자막 필터(ja_only) / 자막 없음 필터가 오래된 캐시 때문에 누락·오분류되는 문제를 막는다.
    폴더 루트 스캔은 생략(사이드카 stem 기준만).
    """
    global _LAMP_STT_REPAIR_DONE
    if _LAMP_STT_REPAIR_DONE and not force:
        return {"checked": 0, "updated": 0, "skipped": 1}

    from sqlalchemy import or_

    from javstory.harvest.database import FileFlagCache, JAVMetadata, get_db_session

    checked = 0
    updated = 0
    session = get_db_session()
    try:
        rows = (
            session.query(FileFlagCache, JAVMetadata)
            .outerjoin(
                JAVMetadata,
                FileFlagCache.product_code == JAVMetadata.product_code,
            )
            .filter(or_(FileFlagCache.lamp_stt == 0, FileFlagCache.lamp_stt.is_(None)))
            .all()
        )
        for cache, meta in rows:
            checked += 1
            if meta is not None and bool(getattr(meta, "is_hardcoded", False)):
                continue
            if not cache.video_path:
                continue
            try:
                vp = Path(cache.video_path)
            except Exception:
                continue
            if _sidecar_has_ja(vp):
                cache.lamp_stt = 1
                updated += 1
        if updated:
            session.commit()
        else:
            session.rollback()
        _LAMP_STT_REPAIR_DONE = True
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()
    return {"checked": checked, "updated": updated, "skipped": 0}


def schedule_lamp_flag_repair(*, need_sub: bool = True, need_stt: bool = True) -> None:
    """자막 필터 API를 막지 않도록 캐시 수리를 백그라운드에서 1회 실행.

    이미 수리 스레드가 돌고 있어도 추가 need_* 는 큐에 쌓아 이어서 처리한다.
    """
    global _LAMP_REPAIR_THREAD, _LAMP_REPAIR_PENDING_SUB, _LAMP_REPAIR_PENDING_STT
    with _LAMP_REPAIR_LOCK:
        if need_sub and not _LAMP_SUB_REPAIR_DONE:
            _LAMP_REPAIR_PENDING_SUB = True
        if need_stt and not _LAMP_STT_REPAIR_DONE:
            _LAMP_REPAIR_PENDING_STT = True
        if not _LAMP_REPAIR_PENDING_SUB and not _LAMP_REPAIR_PENDING_STT:
            return
        t = _LAMP_REPAIR_THREAD
        if t is not None and t.is_alive():
            return

        def _run() -> None:
            global _LAMP_REPAIR_PENDING_SUB, _LAMP_REPAIR_PENDING_STT
            while True:
                with _LAMP_REPAIR_LOCK:
                    do_sub = _LAMP_REPAIR_PENDING_SUB
                    do_stt = _LAMP_REPAIR_PENDING_STT
                    _LAMP_REPAIR_PENDING_SUB = False
                    _LAMP_REPAIR_PENDING_STT = False
                if not do_sub and not do_stt:
                    break
                if do_sub:
                    try:
                        repair_stale_lamp_sub_flags()
                    except Exception:
                        pass
                if do_stt:
                    try:
                        repair_stale_lamp_stt_flags()
                    except Exception:
                        pass

        thread = threading.Thread(target=_run, name="lamp-flag-repair", daemon=True)
        _LAMP_REPAIR_THREAD = thread
        thread.start()


def invalidate_lamp_sub_repair_cache() -> None:
    """호환용 — 자막 생성 후 다음 필터에서 재검사하도록 한다."""
    invalidate_lamp_flag_repair_cache()


def invalidate_lamp_flag_repair_cache() -> None:
    """자막/STT 생성 후 다음 필터에서 lamp_sub·lamp_stt 재검사."""
    global _LAMP_SUB_REPAIR_DONE, _LAMP_STT_REPAIR_DONE
    _LAMP_SUB_REPAIR_DONE = False
    _LAMP_STT_REPAIR_DONE = False
