"""Harvest DB + canonical(library_state.json) 요약 — GUI용 얇은 브리지."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from javstory.library.cover_cache import cover_needs_download, resolve_cover_path
from javstory.library.paths import library_state_path, work_library_dir


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


def scan_videos_in_dir(d: Path, depth=0) -> list[Path]:
    """디렉토리 내 모든 동영상 파일 리스트 반환."""
    if not d.is_dir():
        return []
    from javstory.library.video_ext import is_video_file

    found = []
    # 1단계: 직하위 파일 탐색
    try:
        files = sorted(list(d.iterdir()))
        for p in files:
            if p.is_file() and is_video_file(p):
                found.append(p)
        
        # 2단계: 하위 폴더 재귀 탐색 (최대 깊이 2단계)
        if depth < 2:
            for p in files:
                if p.is_dir():
                    found.extend(scan_videos_in_dir(p, depth + 1))
    except OSError:
        pass
    return found


def _first_video_in_dir(d: Path, depth=0) -> Path | None:
    res = scan_videos_in_dir(d, depth)
    return res[0] if res else None


SELF_SUBTITLE_MARKER = "자체자막"


# 파일·폴더명에 이 문자열만 있을 때 자체자막 램프 (일반 `[자막]` 태그는 제외)
_SELF_SUBTITLE_NAME_RE = re.compile(r"자체\s*자막")

# 모자이크 파괴(모파) 키워드: 폴더/파일명에 포함되면 True
_MOPA_NAME_RE = re.compile(r"(모자이크\s*(삭제|제거|파괴)|uncen|uncensored|reducing\s*mosaic)", re.IGNORECASE)


def path_contains_self_subtitle_marker(video_path: Path | None, folder_path: str | None, product_code: str = "") -> bool:
    """폴더·파일 이름에「자체자막」「자체 자막」연속 문자열만 허용. `[자막]` 단독 등은 제외."""

    target_texts = []
    if video_path:
        target_texts.append(video_path.name)
        target_texts.extend(video_path.parts)

    fp = (folder_path or "").strip()
    if fp:
        try:
            p_fp = Path(fp)
            target_texts.append(p_fp.name)
            target_texts.extend(p_fp.parts)
        except Exception:
            pass

    for text in target_texts:
        if _SELF_SUBTITLE_NAME_RE.search(text):
            return True
    return False


def path_contains_mopa_marker(video_path: Path | None, folder_path: str | None) -> bool:
    """폴더·파일 이름에 모자이크 파괴(모파) 키워드가 있으면 True."""
    target_texts = []
    if video_path:
        target_texts.append(video_path.name)
        target_texts.extend(video_path.parts)

    fp = (folder_path or "").strip()
    if fp:
        try:
            p_fp = Path(fp)
            target_texts.append(p_fp.name)
            target_texts.extend(p_fp.parts)
        except Exception:
            pass

    for text in target_texts:
        if _MOPA_NAME_RE.search(text):
            return True
    return False


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


def guess_video_path_for_product(product_code: str, folder_path: str | None = None) -> Path | None:
    """작품 폴더(DB 저장 경로, 라이브러리, MEDIA_ROOT) 직하위에서 첫 동영상 탐색."""
    res = find_all_video_paths_for_product(product_code, folder_path)
    return res[0] if res else None


def guess_video_path_for_product_fast(product_code: str, folder_path: str | None = None) -> Path | None:
    """[최적화] 연결된 폴더 내부만 체크 (라이브러리/전역 폴더 탐색 생략)."""
    if not folder_path:
        return None
    pc = (product_code or "").strip().upper()
    base = Path(folder_path)
    if not base.is_dir():
        return None
    
    # scan_videos_in_dir는 depth=0이 기본이므로 해당 폴더 직하위만 확인 (빠름)
    videos = scan_videos_in_dir(base)
    for v in videos:
        if pc in v.name.upper():
            return v
    return None


def guess_video_path_for_product_debug(
    product_code: str, folder_path: str | None = None
) -> tuple[Path | None, list[str], list[str]]:
    """
    `guess_video_path_for_product`의 디버그 버전.
    반환: (first_video_or_none, searched_base_dirs, matched_videos)
    - searched_base_dirs: 실제로 검사 대상이 된 base 디렉터리(존재/디렉터리 여부와 무관하게 후보 포함)
    - matched_videos: 품번 포함 규칙(pc in filename)을 통과한 영상 후보들
    """
    pc = (product_code or "").strip().upper()
    if not pc:
        return None, [], []
    bases = _video_search_dirs(pc, folder_path)
    matches = find_all_video_paths_for_product(pc, folder_path)
    first = matches[0] if matches else None
    return first, [str(p) for p in bases], [str(p) for p in matches]


def _video_search_dirs(product_code: str, folder_path: str | None = None) -> list[Path]:
    pc = (product_code or "").strip().upper()
    if not pc:
        return []
    from javstory.config.app_config import E_MEDIA_ROOT, E_DATA_ROOT, MEDIA_ROOT

    search_dirs: list[Path] = []
    if folder_path and Path(folder_path).is_dir():
        search_dirs.append(Path(folder_path))
    search_dirs.extend(
        [
            work_library_dir(pc),
            Path(E_MEDIA_ROOT) / pc,
            Path(E_DATA_ROOT) / pc,
            Path(E_DATA_ROOT) / "media" / pc,
            Path(MEDIA_ROOT) / pc,
        ]
    )
    return search_dirs


def find_all_video_paths_for_product(product_code: str, folder_path: str | None = None) -> list[Path]:
    """작품 폴더들에서 해당 품번과 관련된 모든 동영상 탐색 (멀티파트 대응)."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return []
    search_dirs = _video_search_dirs(pc, folder_path)

    all_found = []
    seen = set()
    
    for base in search_dirs:
        videos = scan_videos_in_dir(base)
        for v in videos:
            if v.absolute() in seen:
                continue
            # 품번이 포함되어 있는지 (대소문자 무시) 확인하여 관련성 체크
            if pc in v.name.upper():
                all_found.append(v)
                seen.add(v.absolute())
    
    return all_found


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


def row_to_summary_fast(row: Any) -> LibraryWorkSummary:
    """I/O를 최소화한 고속 버전 (그리드 목록용)."""
    return _row_to_summary_impl(row, fast=True)


def _row_to_summary_impl(row: Any, fast: bool = False) -> LibraryWorkSummary:
    """SQLAlchemy JAVMetadata 행 → LibraryWorkSummary."""
    pc = (getattr(row, "product_code", None) or "").strip()
    
    # 목록(그리드)에서는 canonical JSON 파싱 비용을 생략하고 존재 여부만 사용한다.
    has_c, n_sc, n_st, prev = canonical_quick_stats(pc, fast=fast)

    title_ko = (getattr(row, "title_ko", None) or getattr(row, "title", None) or "").strip()
    title_ja = (getattr(row, "title_ja", None) or getattr(row, "original_title", None) or "").strip()
    has_harvest = bool(title_ko or title_ja)

    cover_local = getattr(row, "cover_image_local_path", None)
    cover_url = getattr(row, "cover_image_url", None)
    folder_path_raw = getattr(row, "folder_path", None)
    folder_path = (folder_path_raw or "").strip() or None

    has_transcription = False
    has_translation = False
    has_ja_srt = False
    has_ko_srt = False
    lamp_hardcoded = False
    lamp_mopa = bool(getattr(row, "is_mopa", False))

    # [핵심 최적화] 목록(그리드)에서는 전체 탐색을 피한다.
    # 다만 폴더가 연결돼 있는 경우에는 "연결 폴더 내부만" 빠르게 확인하여
    # 사이드카 자막(.ja.srt/.ko.srt/.srt) 존재에 따른 램프/STT·Subtitle 트리거가 동작하도록 한다.
    if fast:
        vp = guess_video_path_for_product_fast(pc, folder_path) if folder_path else None
    else:
        vp = guess_video_path_for_product(pc, folder_path)
    db_hardcoded = bool(getattr(row, "is_hardcoded", False))
    
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
        has_transcription = False
        has_translation = False
        has_ja_srt = False
        has_ko_srt = False
        lamp_hardcoded = db_hardcoded

    stage = _pipeline_stage(
        has_harvest=has_harvest,
        has_transcription=has_transcription,
        has_translation=has_translation,
        has_canonical=has_c,
    )

    eff = resolve_cover_path(pc, cover_local)
    eff_s = str(eff) if eff else None
    
    # 커버 다운로드 필요 여부도 fast 모드에서는 생략 가능 (UI에서 처리)
    need_dl = False if fast else cover_needs_download(pc, cover_url, cover_local)

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
