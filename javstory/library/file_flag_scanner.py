"""작품 파일 상태 스캔 → file_flag_cache 갱신.

row_to_summary_fast()가 매번 수행하던 HDD I/O(작품당 10~15회)를
백그라운드에서 한 번만 수행하고 DB에 캐시해 라이브러리 로딩 속도를 개선한다.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Callable


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
