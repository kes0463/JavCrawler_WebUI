"""
Harvest 코디네이터: 크롤 → 매핑 → 번역 → DB → 자산.

Grok 스토리 맥락 JSON: 메타 `commit` 직후 `Transcription.story_grok_module.run_story_grok_after_harvest_async`
로 `data/cache/story_context/`에 저장(자막 파이프라인과 동일 SoT).
"""
import sys
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Harvest 내부 모듈 임포트
from javstory.harvest.crawler import HybridJavCrawler
from javstory.harvest.database import get_db_session_ctx, upsert_jav_metadata, Genre, Maker
from javstory.harvest.translator import MetadataTranslator
from javstory.utils.actress_resolver import ActressResolver
from javstory.utils.assets_handler import MetadataAssetsHandler
from javstory.config.app_config import story_analysis_enabled_from_env

from javstory.utils.common import log_ts as _log_ts, tagify
from javstory.utils.perf_log import perf_span, log_perf


def log_ts(msg: str):
    _log_ts(msg, tag="Coordinator")


def _script_counts(s: str) -> dict[str, int]:
    """가벼운 언어/스크립트 판별용 카운터 (PII/원문 로그 금지)."""
    txt = (s or "").strip()
    c = {"hangul": 0, "hiragana": 0, "katakana": 0, "cjk": 0, "latin": 0, "digit": 0, "other": 0}
    for ch in txt:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:  # Hangul Syllables
            c["hangul"] += 1
        elif 0x3040 <= o <= 0x309F:  # Hiragana
            c["hiragana"] += 1
        elif 0x30A0 <= o <= 0x30FF:  # Katakana
            c["katakana"] += 1
        elif 0x4E00 <= o <= 0x9FFF:  # CJK Unified Ideographs (Kanji 포함)
            c["cjk"] += 1
        elif (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A):
            c["latin"] += 1
        elif 0x30 <= o <= 0x39:
            c["digit"] += 1
        else:
            c["other"] += 1
    return c


def _looks_like_ko(text: str, *, min_hangul: int = 1) -> bool:
    """KO 필드가 실제로 한국어를 포함하는지(최소 한글 포함) 확인."""
    cnt = _script_counts(text)
    return cnt["hangul"] >= int(min_hangul)


def _looks_like_ja(text: str) -> bool:
    """JA 스크립트(히라가나/가타카나) 또는 CJK 위주면 일본어일 가능성이 높다고 판단."""
    cnt = _script_counts(text)
    return (cnt["hiragana"] + cnt["katakana"]) > 0 or (cnt["cjk"] > 0 and cnt["hangul"] == 0 and cnt["latin"] == 0)


def _harvest_should_run_story_context(explicit: bool | None) -> bool:
    """None이면 `JAVSTORY_STORY_ANALYSIS_ENABLED`와 동일(자막 오케스트레이터 기본과 맞춤)."""
    if explicit is False:
        return False
    if explicit is True:
        return True
    return story_analysis_enabled_from_env()


import threading

# 전역 세마포어: 하베스트(브라우저+LLM) 동시 실행 수를 제한하여 CPU/VRAM 부하 방지
# QThread별로 루프가 달라 asyncio.Semaphore 사용 시 "bound to a different event loop" 에러 발생하므로 threading.Semaphore 사용
_SEMAPHORE_LOCK = threading.Lock()
_HARVEST_SEMAPHORE: threading.Semaphore | None = None

def _get_harvest_semaphore() -> threading.Semaphore:
    global _HARVEST_SEMAPHORE
    with _SEMAPHORE_LOCK:
        if _HARVEST_SEMAPHORE is None:
            import os
            try:
                val = max(1, int(os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "2")))
            except Exception:
                val = 2
            _HARVEST_SEMAPHORE = threading.Semaphore(val)
    return _HARVEST_SEMAPHORE

async def run_crawler_for_video_path(
    video_path: str | Path,
    api_key: str | None = None,
    *,
    product_code: str | None = None,
    enable_story_context: bool | None = None,
    story_context_tier: dict[str, Any] | None = None,
    force_rebuild_story_context: bool = False,
    skip_translation: bool = False,
    skip_media: bool = False,
    translator_instance: Optional[MetadataTranslator] = None,
) -> dict[str, Any]:
    """
    [Phase 1-2 통합] 영상 경로를 받아 크롤링 -> 배우 매핑 -> AI 번역 -> DB 저장 -> 자산 처리까지 수행하는 마스터 파이프라인 (Async).

    `product_code`: 폴더명 기반 품번 등 **명시적 품번**(영상 파일명과 불일치할 때).
    `video_path`가 품번 문자열 단독(파일 없음)일 때는 `product_code`와 동일하게 두면 된다.

    Grok 스토리 맥락 JSON(`enable_story_context` / env): DB 저장 직후 공통 모듈로 생성 — **구현 완료.**
    """
    # [수정] threading.Semaphore를 사용하여 루프와 무관하게 전역 동시 실행 제한 (동작 방식: 슬롯이 생길 때까지 현재 스레드 대기)
    with _get_harvest_semaphore():
        path_obj = Path(video_path)
        explicit = (product_code or "").strip().upper()
        code = explicit or path_obj.stem.upper()
        
        log_ts(f"--- 하베스트 시작: {code} ---")
        log_perf("harvest.start", product_code=code, has_video=bool(path_obj.is_file()))
        
        # [수정] video_path로부터 폴더 경로 추출 (파일이면 부모, 문자열이면 그대로)
        v_path = Path(video_path)
        stored_folder_path = str(v_path.parent.resolve()) if v_path.is_file() else None
        
        crawler = HybridJavCrawler()
        resolver = ActressResolver()
        # translator_instance가 있으면 재사용, 없으면 새로 생성
        translator = translator_instance or MetadataTranslator(api_key=api_key)
        assets_handler = MetadataAssetsHandler()
    
    # === [사전 DB 상태 확인] ===
    needs_crawling = True
    needs_translation = True
    
    raw_title, raw_synopsis, raw_maker = "", "", ""
    raw_actors, raw_genres = [], []
    db_cover_url, db_release_date = "", ""
    db_favorite_score = 0
    db_favorite_sources = None
    original_title = ""
    db_folder_path: str | None = None
    trans_res = {}
    did_translate = False
    # 번역 스킵 판단은 DB가 채워졌는지 뿐 아니라 "KO 필드가 한국어로 저장됐는지"를 함께 본다.
    
    try:
        # [수정] 전체 과정을 try-finally로 감싸 비동기 리소스(httpx 클라이언트 등)의 확실한 해제 보장
        try:
            from javstory.harvest.database import JAVMetadata
            with get_db_session_ctx() as session:
                row = session.query(JAVMetadata).filter_by(product_code=code).first()
                if row:
                    db_folder_path = getattr(row, "folder_path", None)
                    # 1. 원본(JA) 데이터 확인
                    # - 크롤링(웹 수집) 스킵은 커버 URL까지 포함한 "완전한 원본"을 요구한다.
                    # - 번역 스킵은 제목/시놉시스 JA 텍스트만 있으면 충분하다(커버 URL 부재로 번역을 매번 다시 돌지 않게).
                    has_ja_text = all([
                        row.title_ja and row.title_ja.strip(),
                        row.synopsis_ja and row.synopsis_ja.strip(),
                    ])
                    has_ja_full = all([
                        row.title_ja and row.title_ja.strip(),
                        row.synopsis_ja and row.synopsis_ja.strip(),
                        row.cover_image_url and row.cover_image_url.strip(),
                    ])
                    if has_ja_full and not force_rebuild_story_context:
                        needs_crawling = False
                        raw_title = row.title_ja
                        raw_synopsis = row.synopsis_ja
                        raw_maker = row.maker_ja or ""
                        raw_actors = [a.strip() for a in (row.actors_ja or "").split(",") if a.strip()]
                        raw_genres = [g.strip() for g in (row.genres_ja or "").split(",") if g.strip()]
                        raw_genres = [g.strip() for g in (row.genres_ja or "").split(",") if g.strip()]
                        db_cover_url = row.cover_image_url
                        db_release_date = row.release_date or ""
                        original_title = row.original_title or raw_title
                        db_favorite_score = int(getattr(row, "favorite_score", 0) or 0)
                        db_favorite_sources = getattr(row, "favorite_sources", None)
                        log_ts(f"✅ {code} 원본 메타데이터가 완벽하여 웹 수집(크롤링)을 생략합니다.")
                    
                    # 2. 번역(KO) 데이터 확인
                    has_ko_raw = all([
                        row.title_ko and row.title_ko.strip(),
                        row.synopsis_ko and row.synopsis_ko.strip(),
                    ])

                    # [핵심] KO 필드가 "비어있지 않음"만으로는 불충분.
                    # 일본어 원문이 KO 칼럼에 들어간 경우(마이그레이션/초기 저장) 번역을 재시도해야 한다.
                    title_ko = (row.title_ko or "").strip()
                    syn_ko = (row.synopsis_ko or "").strip()
                    ko_title_ok = _looks_like_ko(title_ko, min_hangul=1)
                    ko_syn_ok = _looks_like_ko(syn_ko, min_hangul=2)  # 시놉시스는 2글자 이상 한글 기대
                    ko_is_probably_ja = _looks_like_ja(title_ko) or _looks_like_ja(syn_ko)
                    has_ko_ok = bool(has_ko_raw and ko_title_ok and ko_syn_ok and (not ko_is_probably_ja))

                    # KO 필드가 채워져 있어도 "정해진 언어(한국어)"로 보이지 않으면 번역 필요로 간주
                    if has_ko_raw and (not has_ko_ok):
                        needs_translation = True
                        log_ts(f"⚠️ {code} KO 필드가 한국어로 보이지 않아 번역을 재시도합니다.")

                    # DB에 JA 원본 + KO가 한국어로 올바르게 저장돼 있으면 번역은 스킵(초기값이 True여도 무조건 스킵)
                    if has_ja_text and has_ko_ok and not force_rebuild_story_context:
                        needs_translation = False
                        log_ts(f"✅ {code} 번역 데이터가 완벽하여 AI 번역을 생략합니다.")
        except Exception as e:
            log_ts(f"⚠️ {code} 사전 DB 확인 오류: {e}")

        # 1. 크롤링 (Metadata Ingestion)
        # 재크롤링(force_rebuild_story_context)일 때는 DB 상태와 무관하게 항상 웹 수집을 다시 시도한다.
        if needs_crawling or force_rebuild_story_context:
            with perf_span("harvest.crawl", product_code=code):
                res = await crawler.fetch_metadata_smart(code)
            if not res:
                log_ts(f"⚠️ {code} 크롤링 실패 (데이터 없음). 로컬 표지 및 뼈대 정보 생성 중...")
                
                # [추가] 로컬 폴더에서 가장 적절한 이미지 찾기 (표지 대용)
                local_cover = None
                if stored_folder_path:
                    folder = Path(stored_folder_path)
                    if folder.is_dir():
                        # 1순위: 품번 포함 파일, 2순위: 모든 이미지 중 가장 용량이 큰 것(보통 표지)
                        patterns = [f"*{code}*.jpg", f"*{code}*.png", "*.jpg", "*.png", "*.jpeg", "*.webp"]
                        for pattern in patterns:
                            try:
                                found = list(folder.glob(pattern))
                                if found:
                                    # 파일 크기순 정렬 (가장 큰 것이 고화질 표지일 확률이 높음)
                                    found.sort(key=lambda p: p.stat().st_size, reverse=True)
                                    local_cover = str(found[0].resolve())
                                    break
                            except Exception:
                                continue

                with get_db_session_ctx() as session:
                    upsert_jav_metadata(session, code, 
                        title_ko=f"[{code}] (수집 실패/정보 없음)", 
                        folder_path=(stored_folder_path or db_folder_path),
                        cover_image_local_path=local_cover, # 로컬 이미지 경로 등록
                        analysis_status="FAILED_CRAWL"
                    )
                    session.commit()
                
                return {"error": "crawling_failed", "product_code": code, "skeleton_saved": True}
                
            raw_actors = res.get("actors", [])
            raw_genres = res.get("genres", [])
            raw_title = res.get("title", "")
            raw_synopsis = res.get("synopsis", "")
            raw_maker = res.get("maker", "")
            db_cover_url = res.get("cover_url", "")
            db_release_date = res.get("release_date", "")
            original_title = res.get("original_title") or raw_title
            db_favorite_score = int(res.get("favorite_score") or 0)
            _fav_parts = {
                k.removeprefix("_fav_src_"): v
                for k, v in res.items() if k.startswith("_fav_src_")
            }
            db_favorite_sources = ",".join(
                f"{site}:{score}" for site, score in _fav_parts.items() if score
            ) or None

        # 2. 배우/장르/제작사 해결 (Mapping)
        resolved_actors = resolver.resolve_names(raw_actors) # JA, KO, Romaji
        
        resolved_genres = _resolve_genres(raw_genres)
        resolved_maker = _resolve_maker(raw_maker)
        
        # 3. AI 한국어 번역 (LLM: 제목·시놉시스만 JA→KO, EN/ZH 열은 아래서 일본어 원문 복사)
        # skip_translation이 True이면 여기서 번역을 건너뛴다.
        if (needs_translation or force_rebuild_story_context) and not skip_translation:
            did_translate = True
            approved_terms = {
                "ko": {
                    **{ja: ko for ja, ko in zip(resolved_actors["ja"], resolved_actors["ko"]) if ja != ko},
                    **{ja: ko for ja, ko in zip(resolved_genres["ja"], resolved_genres["ko"]) if ja != ko},
                    **({resolved_maker["ja"]: resolved_maker["ko"]} if resolved_maker["ja"] != resolved_maker["ko"] else {}),
                }
            }
            
            log_ts(f"🚀 AI 한국어 번역 중…")
            with perf_span("harvest.translate", product_code=code):
                trans_res = await translator.translate_metadata_batch(
                    code,
                    raw_title,
                    raw_synopsis,
                    actors=raw_actors,
                    genres=raw_genres,
                    maker=raw_maker,
                    approved_terms=approved_terms,
                )
            # 번역 단계가 필요했는데 결과가 비정상이면 "성공"으로 진행하면 안 된다.
            if not isinstance(trans_res, dict) or not trans_res:
                log_ts(f"❌ {code} 번역 실패: 번역 결과가 비어 있습니다.")
                return {"error": "translation_failed_empty", "product_code": code}
            # 검증:
            # - 제목 KO는 필수
            # - 시놉시스 KO는 "원문 시놉시스가 비어있던 케이스"면 비어있어도 부분 성공으로 허용
            _title_ko = str((trans_res or {}).get("title_ko") or "").strip()
            _syn_ko = str((trans_res or {}).get("synopsis_ko") or "").strip()
            _raw_syn = str(raw_synopsis or "").strip()

            if not _title_ko:
                log_ts(f"❌ {code} 번역 실패: KO 제목이 비어 있습니다.")
                return {"error": "translation_failed_missing_ko", "product_code": code}

            if (not _syn_ko) and (not _raw_syn):
                # 원문 시놉시스 자체가 없어서(혹은 추출 실패) 번역 결과도 KO 시놉시스가 비어 내려오는 케이스
                pass
            elif not _syn_ko:
                log_ts(f"❌ {code} 번역 실패: KO 시놉시스가 비어 있습니다.")
                return {"error": "translation_failed_missing_ko", "product_code": code}

        # 4. DB Upsert (Persistence)
        with perf_span("harvest.db_upsert", product_code=code):
            with get_db_session_ctx() as session:
                # [4-1] 제목·시놉시스: KO는 LLM, title_en / title_zh_* / synopsis_en / synopsis_zh_* 는 일본어 원문과 동일 문자열
                _t_ja = (str(trans_res.get("title_ja") or raw_title) or "").strip() or (raw_title or "")
                _s_ja = (str(trans_res.get("synopsis_ja") or raw_synopsis) or "").strip() or (raw_synopsis or "")
                titles = {
                    "title_ja": _t_ja,
                    "title_ko": trans_res.get("title_ko", raw_title),
                    "title_en": _t_ja,
                    "title_zh_cn": _t_ja,
                    "title_zh_tw": _t_ja,
                }
                synopses = {
                    "synopsis_ja": _s_ja,
                    "synopsis_ko": trans_res.get("synopsis_ko", raw_synopsis),
                    "synopsis_en": _s_ja,
                    "synopsis_zh_cn": _s_ja,
                    "synopsis_zh_tw": _s_ja,
                }

                # 배우·장르·제작사: 마스터 테이블(리졸버) 전용, LLM 병합 없음
                actors_ko = tagify(resolved_actors["ko"])
                actors_romaji = tagify(resolved_actors["romaji"])
                actors_zh_cn = tagify(resolved_actors["zh_cn"])
                actors_zh_tw = tagify(resolved_actors["zh_tw"])

                genres_ko = tagify(resolved_genres["ko"])
                genres_en = tagify(resolved_genres["en"])
                genres_zh_cn = tagify(resolved_genres["zh_cn"])
                genres_zh_tw = tagify(resolved_genres["zh_tw"])

                maker_ko = resolved_maker["ko"]
                maker_en = resolved_maker["en"]
                maker_zh_cn = resolved_maker["zh_cn"]
                maker_zh_tw = resolved_maker["zh_tw"]

                row = upsert_jav_metadata(
                    session,
                    product_code=code,
                    merge_empty_only=not bool(force_rebuild_story_context),
                    **titles,
                    original_title=original_title,
                    **synopses,
                    actors_ja=tagify(resolved_actors["ja"]),
                    actors_ko=actors_ko,
                    actors_romaji=actors_romaji,
                    actors_zh_cn=actors_zh_cn,
                    actors_zh_tw=actors_zh_tw,
                    genres_ja=tagify(resolved_genres["ja"]),
                    genres_ko=genres_ko,
                    genres_en=genres_en,
                    genres_zh_cn=genres_zh_cn,
                    genres_zh_tw=genres_zh_tw,
                    maker_ja=tagify(resolved_maker["ja"]),
                    maker_ko=maker_ko,
                    maker_en=maker_en,
                    maker_zh_cn=maker_zh_cn,
                    maker_zh_tw=maker_zh_tw,
                    cover_image_url=db_cover_url,
                    release_date=tagify(db_release_date),
                    actors=tagify(resolved_actors["ja"]),
                    title=titles["title_ko"],
                    synopsis=synopses["synopsis_ko"],
                    genres=genres_ko,
                    maker=maker_ko,
                    folder_path=(stored_folder_path or db_folder_path),
                    favorite_score=db_favorite_score,
                    favorite_sources=db_favorite_sources,
                )

                # 폴더/영상 경로가 확정되는 시점에 1회 마커 감지 후 DB 저장
                try:
                    from gui.library_data import path_contains_self_subtitle_marker, path_contains_mopa_marker

                    vp = path_obj if path_obj.is_file() else None
                    row.is_hardcoded = bool(path_contains_self_subtitle_marker(vp, stored_folder_path, code))
                    row.is_mopa = bool(path_contains_mopa_marker(vp, stored_folder_path))
                except Exception:
                    pass

                # 5. 자산 처리 (Assets - 표지 다운로드 등)
                with perf_span("harvest.assets.cover", product_code=code):
                    local_cover_path = await assets_handler.download_cover_image(db_cover_url, code)
                if local_cover_path:
                    row.cover_image_local_path = local_cover_path

                session.commit()
                log_ts(f"✅ {code} 수집 및 DB 저장 완료 (한국어 번역 + EN/ZH 제목·시놉은 일본어 원문, 배우·장르·제작사는 DB 매핑)")
                # 주의: SQLAlchemy는 commit 후 객체 속성을 expire할 수 있어,
                # session 종료 후 row.id 접근 시 DetachedInstanceError가 날 수 있다.
                row_id = int(getattr(row, "id", 0) or 0)

            if _harvest_should_run_story_context(enable_story_context):
                from javstory.translation.story_grok_module import run_story_grok_after_harvest_async
                with perf_span("harvest.story_context", product_code=code):
                    await run_story_grok_after_harvest_async(
                        product_code=code,
                        logger_func=log_ts,
                        story_context_tier=story_context_tier,
                        force_refresh=force_rebuild_story_context,
                    )

            # [추가] 스냅샷 및 다이제스트 자동 추출 트리거 (skip_media가 아닐 때만)
            if path_obj.is_file() and not skip_media:
                try:
                    from javstory.library.stills.snapshot_queue import snapshot_queue_manager
                    from javstory.library.stills.digest_queue import digest_queue_manager
                    from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT

                    # 신규 HDD 루트 우선, 없으면 레거시 루트로 생성/사용
                    base_root = Path(E_MEDIA_ROOT)
                    try:
                        base_root.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        base_root = Path(MEDIA_ROOT)

                    out_dir = base_root / code / "Snapshots"
                    existing = list(out_dir.glob("snapshot_*.jpg"))
                    if len(existing) < 5: 
                        log_ts(f"📸 스냅샷 백그라운드 큐 등록 ({code})...")
                        log_perf("snapshots.enqueue", product_code=code, out_dir=str(out_dir))
                        snapshot_queue_manager.push_job(path_obj, out_dir, product_code=code)

                    digest_dir = base_root / code / "Digest"
                    digest_dir.mkdir(parents=True, exist_ok=True)
                    digest_path = digest_dir / "digest.mp4"
                    if not digest_path.exists():
                        log_ts(f"🎥 다이제스트 백그라운드 큐 등록 ({code})...")
                        log_perf("digest.enqueue", product_code=code, out=str(digest_path))
                        digest_queue_manager.push_job(path_obj, digest_path, product_code=code)

                    # Golden Preview(WebP) 자동 큐 등록 (존재 시 스킵)
                    try:
                        from gui.models.preview_queue_model import PreviewQueueController
                        pq = PreviewQueueController.instance()
                        if pq:
                            log_perf("preview.enqueue", product_code=code)
                            pq.enqueue(code, str(path_obj))
                    except Exception:
                        pass
                except Exception as e:
                    log_ts(f"⚠️ 추가 미디어 구성(스냅샷/다이제스트) 도중 오류: {e}")

            translation_skipped = bool(skip_translation or (not needs_translation and not force_rebuild_story_context))
            if skip_translation:
                skip_reason = "skip_translation_param"
            elif translation_skipped and (not did_translate):
                skip_reason = "already_ok_in_db"
            else:
                skip_reason = ""

            return {
                "status": "success",
                "product_code": code,
                "row_id": row_id,
                "did_translate": bool(did_translate),
                "translation_skipped": bool(translation_skipped),
                "translation_skip_reason": skip_reason,
            }
    except Exception as e:
        log_ts(f"❌ {code} 처리 중 오류 발생: {e}")
        return {"error": str(e), "product_code": code}
    finally:
        # [핵심] 작업이 끝나면 (성공/실패 상관없이) 번역 엔진 명시적 종료
        # 단, 외부에서 전달받은 인스턴스인 경우는 호출처에서 관리하도록 닫지 않음
        if translator_instance is None:
            try:
                await translator.close()
            except Exception:
                pass

def _resolve_genres(japanese_genres: str | list) -> dict:
    """genres 마스터 테이블 매핑 (JA -> KO, EN, ZH) | 미매핑 시 pending 상태로 저장"""
    if isinstance(japanese_genres, str):
        ja_list = [g.strip() for g in japanese_genres.split(",") if g.strip()]
    else:
        ja_list = [str(g).strip() for g in (japanese_genres or []) if str(g).strip()]
        
    ko_list, en_list = [], []
    with get_db_session_ctx() as session:
        try:
            for name in ja_list:
                row = session.query(Genre).filter_by(japanese=name).first()
                if row:
                    ko_list.append(row.korean or name)   # None이면 일본어 폴백
                    en_list.append(row.english or name)  # None이면 일본어 폴백
                else:
                    # [Pending 추가] 미매핑 장르 발견 → korean/english는 NULL 유지
                    new_genre = Genre(japanese=name, korean=None, english=None, needs_review=True)
                    session.add(new_genre)
                    session.commit()
                    ko_list.append(name)  # 폴백: 일본어 원문
                    en_list.append(name)  # 폴백: 일본어 원문
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            print(f"[Coordinator] Genre Resolve Error: {e}")
    
    # ZH(중국어)는 요청에 따라 EN(영어) 필드를 그대로 사용
    return {"ja": ja_list, "ko": ko_list, "en": en_list, "zh_cn": en_list, "zh_tw": en_list}

def _resolve_maker(japanese_maker: str) -> dict:
    """makers 마스터 테이블 매핑 (JA -> KO, EN, ZH) | 미매핑 시 pending 상태로 저장"""
    name = (japanese_maker or "").strip()
    with get_db_session_ctx() as session:
        try:
            row = session.query(Maker).filter_by(japanese=name).first()
            if row:
                ko_val = row.korean or name   # None이면 일본어 폴백
                en_val = row.english or name  # None이면 일본어 폴백
                return {
                    "ja": name, "ko": ko_val, "en": en_val, "zh_cn": en_val, "zh_tw": en_val
                }
            
            # [Pending 추가] 미매핑 제작사 발견 → korean/english는 NULL 유지
            if name:
                new_maker = Maker(japanese=name, korean=None, english=None, slug=name, needs_review=True)
                session.add(new_maker)
                session.commit()
                
            return {"ja": name, "ko": name, "en": name, "zh_cn": name, "zh_tw": name}  # 폴백
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            print(f"[Coordinator] Maker Resolve Error: {e}")
            return {"ja": name, "ko": name, "en": name, "zh_cn": name, "zh_tw": name}

async def run_crawler_phase(sku_list: List[str], is_path: bool = False, loop=None):
    """배치 실행을 위한 래퍼 함수 (Async)"""
    tasks = []
    for sku in sku_list:
        # sku가 경로인지 코드인지에 따라 처리
        tasks.append(run_crawler_for_video_path(sku))
    
    results = await asyncio.gather(*tasks)
    return results

if __name__ == "__main__":
    # 간단한 테스트 실행
    asyncio.run(run_crawler_for_video_path("DASS-026"))
