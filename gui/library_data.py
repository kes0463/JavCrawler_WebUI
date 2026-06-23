"""Harvest DB + canonical(library_state.json) 요약 — GUI용 얇은 브리지."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from javstory.library.cover_cache import cover_needs_download, resolve_cover_path
from javstory.library.paths import library_state_path, work_library_dir
from javstory.library.video_discovery import (
    first_video_in_dir as _first_video_in_dir,
    guess_video_path_for_product_fast,
    scan_videos_in_dir,
)


def find_all_video_paths_for_product(
    product_code: str,
    folder_path: str | None = None,
) -> list[Path]:
    """P3: L4 parts > video_files (flag) > 디스크 탐색."""
    from javstory.harvest.product_repository import resolve_video_paths_for_playback

    return resolve_video_paths_for_playback(product_code, folder_path)


def guess_video_path_for_product(
    product_code: str,
    folder_path: str | None = None,
) -> Path | None:
    paths = find_all_video_paths_for_product(product_code, folder_path)
    return paths[0] if paths else None


@dataclass
class LibraryWorkSummary:
    product_code: str
    title_ko: str
    title_ja: str
    actors_ko: str
    maker_ko: str
    release_date: str
    synopsis_ko: str
    genres_ko: str
    cover_local_path: str | None
    cover_image_url: str | None
    has_canonical: bool
    scene_count: int
    still_total: int
    overall_summary_preview: str
    # --- 확장: 파이프라인·표지·정렬 ---
    has_harvest: bool
    has_transcription: bool
    has_translation: bool
    is_hardcoded: bool
    is_mopa: bool
    has_ja_srt: bool
    has_ko_srt: bool
    lamp_hardcoded: bool
    lamp_mopa: bool
    pipeline_stage: Literal["none", "harvest", "transcription", "translation", "canonical"]
    cover_effective_path: str | None
    cover_needs_download_flag: bool
    updated_at_iso: str
    folder_path: str | None
    favorite_score: int = 0
    has_story_context: bool = False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ── 가벼운 프로세스 내 캐시 ─────────────────────────────────────────────
# 라이브러리 목록 로드(최대 수천건)에서 동일한 `library_state.json`를 반복적으로 읽는 비용을 줄인다.
# - key: product_code(upper)
# - value: (mtime_ns, size, (has, scene_count, still_total, preview))
_CANON_QUICK_CACHE: dict[str, tuple[int, int, tuple[bool, int, int, str]]] = {}


def preference_score(
    favorite_score: int | float | None,
    *,
    liked: bool = False,
    rating: int | float | None = 0,
) -> float:
    """사이트 좋아요, 사용자 하트, 별점을 합친 라이브러리 선표시 점수."""
    try:
        fav = max(0.0, float(favorite_score or 0))
    except Exception:
        fav = 0.0
    try:
        rate = max(0.0, min(5.0, float(rating or 0)))
    except Exception:
        rate = 0.0
    return (math.log1p(fav) * 120.0) + (1800.0 if liked else 0.0) + (rate * 350.0)


def _base_product_code(product_code: str) -> str:
    try:
        from javstory.utils.product_code import strip_split_suffixes

        pc = (product_code or "").strip().upper()
        return strip_split_suffixes(pc) or pc
    except Exception:
        return (product_code or "").strip().upper()


def canonical_quick_stats(product_code: str, *, fast: bool = False) -> tuple[bool, int, int, str]:
    """
    (library_state 존재, 씬 수, 스틸 합계, overall_summary 앞부분)

    fast=True 이면 **파일 존재 여부만** 확인하고, JSON 파싱/씬·스틸 카운트는 생략한다.
    (목록 그리드 진입 속도/디스크 I/O 최적화용)
    """
    pc = (product_code or "").strip().upper()
    if not pc:
        return False, 0, 0, ""

    p = library_state_path(pc)
    try:
        st = p.stat() if p.is_file() else None
    except OSError:
        st = None
    if st is None:
        return False, 0, 0, ""

    if fast:
        # 목록(그리드)에서는 JSON 파싱 비용이 커서 생략한다.
        # 상세 화면 진입 시 `loadDetail()`에서 실제 JSON을 읽어 정확한 값을 표시한다.
        return True, 0, 0, ""

    cached = _CANON_QUICK_CACHE.get(pc)
    if cached and cached[0] == getattr(st, "st_mtime_ns", 0) and cached[1] == int(st.st_size):
        return cached[2]

    d = _read_json(p)
    scenes = d.get("scenes") if isinstance(d.get("scenes"), list) else []
    n_stills = 0
    for s in scenes:
        if isinstance(s, dict):
            sp = s.get("still_paths")
            if isinstance(sp, list):
                n_stills += len(sp)
    summary = (d.get("overall_summary") or "").strip().replace("\n", " ")
    prev = summary[:200] + ("…" if len(summary) > 200 else "")
    res = (True, len(scenes), n_stills, prev)
    _CANON_QUICK_CACHE[pc] = (getattr(st, "st_mtime_ns", 0), int(st.st_size), res)
    return res


from javstory.library.path_markers import (  # noqa: F401 — 하위 호환 re-export
    SELF_SUBTITLE_MARKER,
    path_contains_mopa_marker,
    path_contains_self_subtitle_marker,
)


def _sidecar_srt_flags(video_path: Path) -> tuple[bool, bool, bool]:
    stem = str(video_path.with_suffix(""))
    ja = Path(stem + ".ja.srt").is_file()
    ko = Path(stem + ".ko.srt").is_file()
    plain = Path(stem + ".srt").is_file()
    return ja, ko, plain


def file_rule_lamp_stt_sub(ja: bool, ko: bool, plain: bool) -> tuple[bool, bool]:
    """
    영상과 같은 stem의 `.ja.srt` / `.ko.srt` / `.srt` 존재만으로 STT·Subtitle 램프 규칙.
    (ja+ko → 둘 다, ja만 → STT만, ko만 또는 plain만(일반 .srt) → Subtitle만 등)
    """
    if ja and ko:
        return True, True
    if ja:
        return True, False
    if ko:
        return False, True
    if plain:
        return False, True
    return False, False


def _scan_data_media_srt_flags(product_code: str) -> tuple[bool, bool, bool]:
    """
    `data/media/<품번>/` 아래 트리에 자막 파일이 있는지.
    영상 파일을 찾지 못했거나 사이드카와 무관한 위치에 산출물만 있을 때 카드 램프 보강용.
    """
    from javstory.config.app_config import E_MEDIA_ROOT, E_DATA_ROOT, MEDIA_ROOT

    pc = (product_code or "").strip().upper()
    if not pc:
        return False, False, False
    roots = [
        Path(E_MEDIA_ROOT) / pc,
        Path(E_DATA_ROOT) / pc,
        Path(E_DATA_ROOT) / "media" / pc,
        Path(MEDIA_ROOT) / pc,
    ]
    root = None
    for r in roots:
        if r.is_dir():
            root = r
            break
    if root is None:
        return False, False, False
    has_ja = has_ko = has_plain = False
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            n = p.name.lower()
            if n.endswith(".ja.srt"):
                has_ja = True
            elif n.endswith(".ko.srt"):
                has_ko = True
            elif n.endswith(".srt"):
                has_plain = True
            if has_ja and has_ko and has_plain:
                break
    except OSError:
        pass
    return has_ja, has_ko, has_plain


def _merge_lamp_with_media_artifacts(
    fstt: bool,
    fsub: bool,
    effective_hardcoded: bool,
    product_code: str,
) -> tuple[bool, bool, bool]:
    mj, mk, mpl = _scan_data_media_srt_flags(product_code)
    m_stt, m_sub = file_rule_lamp_stt_sub(mj, mk, mpl)
    return (bool(fstt or m_stt), bool(fsub or m_sub), effective_hardcoded)


def compute_library_lamp_flags(
    *,
    product_code: str,
    video_path: Path | None,
    folder_path: str | None,
    db_is_hardcoded: bool,
    fast: bool = False,
    has_harvest: bool = True,
) -> tuple[bool, bool, bool]:
    """
    라이브러리 그리드/상세의 STT·Subtitle·자체자막 램프 (done/pending).
    fast=True 이면 무거운 디스크 탐색(rglob)과 중복 DB 조회를 생략함.
    """
    pc = (product_code or "").strip().upper()
    vp = video_path
    
    # 자체자막 여부 판단 (fast 모드에서는 DB 값 우선)
    effective_hardcoded = bool(db_is_hardcoded)
    if not fast and not effective_hardcoded:
        effective_hardcoded = path_contains_self_subtitle_marker(vp, folder_path, "")
 
    if effective_hardcoded:
        return False, False, True

    from javstory.pipeline.orchestrator import get_pipeline_status

    # 1. 폴더 미연결 상태
    if vp is None or not vp.is_file():
        if fast:
            # fast 모드에서는 미연결 항목의 외부 산출물(rglob) 체크를 생략하여 성능 확보.
            # 다만 파이프라인 상태(앱 산출물 캐시/DB 기반)는 사용해 램프가 완전히 죽지 않게 한다.
            st = get_pipeline_status(product_code=pc, video_path=None, harvest_ok=has_harvest)
            return (
                bool(st.ja_srt_exists),
                bool(st.ko_srt_exists or st.srt_fallback_exists),
                effective_hardcoded,
            )
            
        st = get_pipeline_status(product_code=pc, video_path=None, harvest_ok=has_harvest)
        return _merge_lamp_with_media_artifacts(
            bool(st.ja_srt_exists),
            bool(st.ko_srt_exists or st.srt_fallback_exists),
            effective_hardcoded,
            pc,
        )

    # 2. 폴더 연결 상태
    # get_pipeline_status는 내부 DB 조회를 생략하도록 harvest_ok 전달
    st = get_pipeline_status(product_code=pc, video_path=vp, harvest_ok=has_harvest)
    ja, ko, pl = _sidecar_srt_flags(vp)
    
    # 별도 자막 파일이 없는 경우 상위 단계(STT/Sub)는 앱 산출물 캐시 활용
    if not ja and not ko and not pl:
        if fast:
            # fast 모드에서는 사이드카가 없으면 앱 산출물(rglob) 체크 생략
            return bool(st.ja_srt_exists), bool(st.ko_srt_exists or st.srt_fallback_exists), effective_hardcoded
            
        return _merge_lamp_with_media_artifacts(
            bool(st.ja_srt_exists),
            bool(st.ko_srt_exists or st.srt_fallback_exists),
            effective_hardcoded,
            pc,
        )

    # 3. 별도 자막 파일 시스템 규칙 적용
    fstt, fsub = file_rule_lamp_stt_sub(ja, ko, pl)
    
    if fast:
        # fast 모드에서는 rglob 보강 없이 기본 규칙만 반환
        return fstt, fsub, effective_hardcoded
        
    return _merge_lamp_with_media_artifacts(fstt, fsub, effective_hardcoded, pc)

    # 3. 폴더 연결 상태
    st = get_pipeline_status(product_code=pc, video_path=vp)
    ja, ko, pl = _sidecar_srt_flags(vp)
    
    # 별도 자막 파일이 없는 경우 상위 단계(STT/Sub)는 앱 산출물 캐시 활용
    if not ja and not ko and not pl:
        return _merge_lamp_with_media_artifacts(
            bool(st.ja_srt_exists),
            bool(st.ko_srt_exists or st.srt_fallback_exists),
            effective_hardcoded,
            pc,
        )

    # 4. 별도 자막 파일 시스템 규칙 적용
    fstt, fsub = file_rule_lamp_stt_sub(ja, ko, pl)
    return _merge_lamp_with_media_artifacts(fstt, fsub, effective_hardcoded, pc)


def _pipeline_stage(
    *,
    has_harvest: bool,
    has_transcription: bool,
    has_translation: bool,
    has_canonical: bool,
) -> Literal["none", "harvest", "transcription", "translation", "canonical"]:
    if has_canonical:
        return "canonical"
    if has_translation:
        return "translation"
    if has_transcription:
        return "transcription"
    if has_harvest:
        return "harvest"
    return "none"


def _row_updated_at_iso(row: Any) -> str:
    u = getattr(row, "updated_at", None)
    if isinstance(u, datetime):
        return u.replace(microsecond=0).isoformat()
    return ""


def row_to_summary(row: Any) -> LibraryWorkSummary:
    return _row_to_summary_impl(row, fast=False)


def row_to_summary_fast(row: Any, *, flags: dict | None = None) -> LibraryWorkSummary:
    """I/O를 최소화한 고속 버전 (그리드 목록용).

    flags가 제공되면 file_flag_cache에서 읽은 값을 사용해 HDD I/O를 완전히 생략한다.
    flags가 None이면 기존 방식(파일 시스템 직접 확인)으로 fallback.
    """
    return _row_to_summary_impl(row, fast=True, flags=flags)


def _row_to_summary_impl(row: Any, fast: bool = False, flags: dict | None = None) -> LibraryWorkSummary:
    """SQLAlchemy JAVMetadata 행 → LibraryWorkSummary."""
    pc = (getattr(row, "product_code", None) or "").strip()

    title_ko = (getattr(row, "title_ko", None) or getattr(row, "title", None) or "").strip()
    title_ja = (getattr(row, "title_ja", None) or getattr(row, "original_title", None) or "").strip()
    has_harvest = bool(title_ko or title_ja)

    cover_local = getattr(row, "cover_image_local_path", None)
    cover_url = getattr(row, "cover_image_url", None)
    folder_path_raw = getattr(row, "folder_path", None)
    folder_path = (folder_path_raw or "").strip() or None
    db_hardcoded = bool(getattr(row, "is_hardcoded", False))
    lamp_mopa = bool(getattr(row, "is_mopa", False))

    if flags is not None:
        # ── 캐시 경로: HDD I/O 없이 DB에서 읽은 플래그 사용 ──────────────
        has_c = bool(flags.get("has_canonical", 0))
        n_sc, n_st, prev = 0, 0, ""
        vp_str = flags.get("video_path")
        vp = Path(vp_str) if vp_str else None
        lamp_stt = bool(flags.get("lamp_stt", 0))
        lamp_sub = bool(flags.get("lamp_sub", 0))
        lamp_hardcoded = db_hardcoded
        has_ja_srt = lamp_stt
        has_ko_srt = lamp_sub
        has_transcription = lamp_stt
        has_translation = lamp_sub
        has_story_context = bool(flags.get("has_story", 0))
    else:
        # ── Fallback: 기존 방식 (캐시 미스 시 파일 시스템 직접 확인) ────────
        has_c, n_sc, n_st, prev = canonical_quick_stats(pc, fast=fast)
        if fast:
            vp = guess_video_path_for_product_fast(pc, folder_path) if folder_path else None
        else:
            vp = guess_video_path_for_product(pc, folder_path)
        lamp_hardcoded = False
        has_ja_srt = False
        has_ko_srt = False
        has_transcription = False
        has_translation = False
        try:
            lamp_stt, lamp_sub, lamp_hardcoded = compute_library_lamp_flags(
                product_code=pc,
                video_path=vp,
                folder_path=folder_path,
                db_is_hardcoded=db_hardcoded,
                fast=fast,
                has_harvest=has_harvest,
            )
            has_ja_srt = lamp_stt
            has_ko_srt = lamp_sub
            has_transcription = lamp_stt
            has_translation = lamp_sub
        except Exception:
            lamp_hardcoded = db_hardcoded
        has_story_context = False
        try:
            from javstory.translation.story_grok_module import has_disk_grok_story_cache
            has_story_context = bool(has_disk_grok_story_cache(pc))
        except Exception:
            pass

    stage = _pipeline_stage(
        has_harvest=has_harvest,
        has_transcription=has_transcription,
        has_translation=has_translation,
        has_canonical=has_c,
    )

    if fast:
        # 고속 경로: 행당 디스크 stat 금지.
        #  1) 플래그 캐시에 해석된 cover_path가 있으면 그대로 사용
        #  2) 없으면 DB의 cover_local_path를 검증 없이 신뢰(파이프라인이 기록한 값)
        #  3) 둘 다 없으면 빈 값(백그라운드 플래그 재스캔이 채움)
        cached_cover = (flags or {}).get("cover_path") if flags is not None else None
        eff_s = (cached_cover or "").strip() or (cover_local or None)
        need_dl = False
    else:
        eff = resolve_cover_path(pc, cover_local)
        eff_s = str(eff) if eff else None
        need_dl = cover_needs_download(pc, cover_url, cover_local)

    return LibraryWorkSummary(
        product_code=pc,
        title_ko=title_ko,
        title_ja=title_ja,
        actors_ko=(getattr(row, "actors_ko", None) or getattr(row, "actors", None) or "").strip(),
        maker_ko=(getattr(row, "maker_ko", None) or getattr(row, "maker", None) or "").strip(),
        release_date=(getattr(row, "release_date", None) or "").strip(),
        synopsis_ko=(getattr(row, "synopsis_ko", None) or getattr(row, "synopsis", None) or "").strip(),
        genres_ko=(getattr(row, "genres_ko", None) or getattr(row, "genres", None) or "").strip(),
        cover_local_path=cover_local,
        cover_image_url=cover_url,
        has_canonical=has_c,
        scene_count=n_sc,
        still_total=n_st,
        overall_summary_preview=prev,
        has_harvest=has_harvest,
        has_transcription=has_transcription,
        has_translation=has_translation,
        is_hardcoded=bool(getattr(row, "is_hardcoded", False)),
        is_mopa=bool(getattr(row, "is_mopa", False)),
        has_ja_srt=has_ja_srt,
        has_ko_srt=has_ko_srt,
        lamp_hardcoded=lamp_hardcoded,
        lamp_mopa=lamp_mopa,
        pipeline_stage=stage,
        cover_effective_path=eff_s,
        cover_needs_download_flag=need_dl,
        updated_at_iso=_row_updated_at_iso(row),
        folder_path=folder_path,
        favorite_score=int(getattr(row, "favorite_score", 0) or 0),
        has_story_context=has_story_context,
    )


def load_library_summaries_from_session(session, *, limit: int = 800) -> list[LibraryWorkSummary]:
    """풀 스캔 요약 (상세 로딩 등)."""
    from javstory.harvest.database import JAVMetadata
    rows = session.query(JAVMetadata).order_by(JAVMetadata.updated_at.desc()).limit(limit).all()
    return [row_to_summary(r) for r in rows]


def load_library_summaries_fast(session, *, limit: int = 2000) -> list[LibraryWorkSummary]:
    """초고속 요약 (라이브러리 메인 목록용)."""
    from javstory.harvest.database import JAVMetadata
    rows = session.query(JAVMetadata).order_by(JAVMetadata.updated_at.desc()).limit(limit).all()
    return [row_to_summary_fast(r) for r in rows]


def load_library_summaries_fast_paged(
    session,
    *,
    limit: int = 400,
    offset: int = 0,
) -> list[LibraryWorkSummary]:
    """초고속 요약 (페이지 단위)."""
    from javstory.harvest.database import JAVMetadata

    q = session.query(JAVMetadata).order_by(JAVMetadata.updated_at.desc())
    if offset:
        q = q.offset(int(max(0, offset)))
    # limit<=0이면 전체 로드(페이지네이션 비활성)
    if int(limit) <= 0:
        rows = q.all()
    else:
        rows = q.limit(int(max(1, limit))).all()
    return [row_to_summary_fast(r) for r in rows]


# 선호도 랭킹 캐시: 동일 데이터 상태에서 loadMore가 매 페이지마다 전체 테이블을
# 재스캔·재정렬하는 O(N²)를 막는다. (모듈 전역 — reload 워커가 새 세션으로 호출)
_PRIORITY_RANKING_CACHE: dict[str, Any] = {}


def invalidate_priority_ranking_cache() -> None:
    """데이터 변경(하베스트/재동기화/시청 갱신)을 알 때 강제 무효화."""
    _PRIORITY_RANKING_CACHE.clear()


def _priority_ranking_signature(session, excl_raw: frozenset[str]) -> tuple:
    """랭킹 캐시 유효성 판단용 경량 시그니처(COUNT/MAX만 사용)."""
    from sqlalchemy import func
    from javstory.harvest.database import JAVMetadata, WatchHistory

    meta_count = session.query(func.count(JAVMetadata.product_code)).scalar() or 0
    meta_max = session.query(func.max(JAVMetadata.updated_at)).scalar()
    watch_count = session.query(func.count(WatchHistory.product_code)).scalar() or 0
    watch_max = session.query(func.max(WatchHistory.updated_at)).scalar()
    return (int(meta_count), str(meta_max), int(watch_count), str(watch_max), excl_raw)


def _compute_priority_ranking(session, excl_raw: set[str]) -> list[tuple[float, Any, str]]:
    from javstory.harvest.database import JAVMetadata, WatchHistory

    excl_base = {_base_product_code(pc) for pc in excl_raw}

    watch_by_base: dict[str, dict[str, Any]] = {}
    try:
        watch_rows = session.query(
            WatchHistory.product_code,
            WatchHistory.liked,
            WatchHistory.rating,
            WatchHistory.updated_at,
        ).all()
        for pc, liked, rating, updated_at in watch_rows:
            base = _base_product_code(str(pc or ""))
            if not base:
                continue
            rec = watch_by_base.get(base)
            rating_i = int(rating or 0)
            liked_b = bool(liked)
            if not rec:
                watch_by_base[base] = {
                    "liked": liked_b,
                    "rating": rating_i,
                    "updated_at": updated_at,
                }
                continue
            rec["liked"] = bool(rec.get("liked")) or liked_b
            rec["rating"] = max(int(rec.get("rating") or 0), rating_i)
            if updated_at and (not rec.get("updated_at") or updated_at > rec.get("updated_at")):
                rec["updated_at"] = updated_at
    except Exception:
        watch_by_base = {}

    meta_rows = session.query(
        JAVMetadata.product_code,
        JAVMetadata.favorite_score,
        JAVMetadata.updated_at,
    ).all()

    ranked: list[tuple[float, Any, str]] = []
    for pc_raw, fav, updated_at in meta_rows:
        pc = str(pc_raw or "").strip().upper()
        if not pc:
            continue
        base = _base_product_code(pc)
        if pc in excl_raw or base in excl_base:
            continue
        wm = watch_by_base.get(base) or {}
        score = preference_score(
            fav,
            liked=bool(wm.get("liked")),
            rating=int(wm.get("rating") or 0),
        )
        ranked.append((score, updated_at, pc))

    ranked.sort(key=lambda it: (it[0], it[1] or datetime.min, it[2]), reverse=True)
    return ranked


def load_library_summaries_fast_priority_paged(
    session,
    *,
    limit: int = 400,
    offset: int = 0,
    exclude_product_codes: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[list[LibraryWorkSummary], bool, int]:
    """선호도 점수순으로 가벼운 우선순위 페이지를 만든 뒤 해당 행만 요약화한다.

    랭킹(전체 정렬)은 데이터 상태가 같으면 재계산하지 않고 캐시에서 슬라이스해
    loadMore() 반복 호출이 O(N²)가 되지 않도록 한다.

    반환: (요약 목록, 랭킹에 다음 페이지가 더 있는지, 이번에 소비한 랭킹 슬롯 수)
    """
    excl_raw = {
        str(pc or "").strip().upper()
        for pc in (exclude_product_codes or [])
        if str(pc or "").strip()
    }
    excl_key = frozenset(excl_raw)

    ranked: list[tuple[float, Any, str]] | None = None
    try:
        sig = _priority_ranking_signature(session, excl_key)
        cached = _PRIORITY_RANKING_CACHE.get("entry")
        if cached and cached.get("sig") == sig:
            ranked = cached.get("ranked")
        else:
            ranked = _compute_priority_ranking(session, excl_raw)
            _PRIORITY_RANKING_CACHE["entry"] = {"sig": sig, "ranked": ranked}
    except Exception:
        ranked = _compute_priority_ranking(session, excl_raw)

    start = int(max(0, offset))
    end = start + int(max(1, limit))
    page_codes = [pc for _, _, pc in (ranked or [])[start:end]]
    if not page_codes:
        return [], False, 0

    from javstory.harvest.database import JAVMetadata
    from sqlalchemy.orm import load_only

    # row_to_summary_fast(flags 경로)가 실제 접근하는 컬럼만 적재한다.
    # 누락 컬럼은 절대 접근하지 않으므로 지연로딩(N+1)이 발생하지 않고,
    # raw_html 등 대형 미사용 컬럼 하이드레이션을 건너뛴다.
    rows = (
        session.query(JAVMetadata)
        .options(
            load_only(
                JAVMetadata.product_code,
                JAVMetadata.title_ko,
                JAVMetadata.title,
                JAVMetadata.title_ja,
                JAVMetadata.original_title,
                JAVMetadata.actors_ko,
                JAVMetadata.actors,
                JAVMetadata.maker_ko,
                JAVMetadata.maker,
                JAVMetadata.release_date,
                JAVMetadata.synopsis_ko,
                JAVMetadata.synopsis,
                JAVMetadata.genres_ko,
                JAVMetadata.genres,
                JAVMetadata.cover_image_local_path,
                JAVMetadata.cover_image_url,
                JAVMetadata.folder_path,
                JAVMetadata.is_hardcoded,
                JAVMetadata.is_mopa,
                JAVMetadata.favorite_score,
                JAVMetadata.updated_at,
            )
        )
        .filter(JAVMetadata.product_code.in_(page_codes))
        .all()
    )
    by_code = {
        str(getattr(row, "product_code", "") or "").strip().upper(): row
        for row in rows
    }

    # 파일 플래그 캐시 일괄 로드 (단일 쿼리, HDD I/O 없음)
    flags_by_code: dict[str, dict] = {}
    try:
        from javstory.library.file_flag_scanner import load_flags_for_codes
        flags_by_code = load_flags_for_codes(session, page_codes)
    except Exception:
        pass

    summaries = [
        row_to_summary_fast(by_code[pc], flags=flags_by_code.get(pc))
        for pc in page_codes
        if pc in by_code
    ]
    has_more = end < len(ranked or [])
    return summaries, has_more, len(page_codes)


SortKey = Literal["updated", "product_code", "release_date", "scene_count"]


def sort_summaries(
    items: list[LibraryWorkSummary],
    key: SortKey = "updated",
    *,
    reverse: bool = True,
) -> list[LibraryWorkSummary]:
    """정렬된 새 리스트 반환."""
    out = list(items)

    def sort_key(s: LibraryWorkSummary) -> Any:
        if key == "updated":
            return s.updated_at_iso or ""
        if key == "product_code":
            return s.product_code.upper()
        if key == "release_date":
            return s.release_date or ""
        if key == "scene_count":
            return s.scene_count
        return ""

    out.sort(key=sort_key, reverse=reverse)
    return out


CanonicalFilter = Literal["all", "has_canonical", "no_canonical"]


def filter_summaries(
    items: list[LibraryWorkSummary],
    *,
    canonical_filter: CanonicalFilter = "all",
    text_query: str = "",
) -> list[LibraryWorkSummary]:
    q = (text_query or "").strip().lower()
    out: list[LibraryWorkSummary] = []
    for s in items:
        if canonical_filter == "has_canonical" and not s.has_canonical:
            continue
        if canonical_filter == "no_canonical" and s.has_canonical:
            continue
        if q:
            blob = f"{s.product_code} {s.title_ko} {s.actors_ko} {s.maker_ko}".lower()
            if q not in blob:
                continue
        out.append(s)
    return out
