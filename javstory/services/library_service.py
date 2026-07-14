from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import aliased

from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT, MEDIA_ROOT
from javstory.harvest.database import FileFlagCache, JAVMetadata, WatchHistory, get_db_session_ctx
from javstory.library.path_markers import (
    path_contains_mopa_marker,
    path_contains_self_subtitle_marker,
)
from javstory.library.paths import library_root
from javstory.library.service import load_work
from javstory.library.genre_filter import aggregate_genre_counts, apply_genre_filters
from javstory.library.snapshots import discover_snapshot_paths

_SAFE_IMAGE_ROOTS = tuple(
    p.resolve()
    for p in (DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT, MEDIA_ROOT, library_root())
    if p
)

_SORT_COLS = {
    "updated_at": JAVMetadata.updated_at,
    "created_at": JAVMetadata.created_at,
    "release_date": JAVMetadata.release_date,
    "product_code": JAVMetadata.product_code,
    "title_ko": JAVMetadata.title_ko,
    "favorite_score": JAVMetadata.favorite_score,
}

HARVEST_FAILED_TITLE_MARKER = "(수집 실패/정보 없음)"

_STATS_CACHE: tuple[float, dict[str, int]] | None = None
_STATS_CACHE_TTL_SEC = 30.0

_GENRES_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_GENRES_CACHE_TTL_SEC = 60.0


def _failed_crawl_filter():
    """크롤 실패 placeholder — SQL NULL 안전(negation 시 UNKNOWN 방지)."""
    return or_(
        JAVMetadata.analysis_status == "FAILED_CRAWL",
        and_(
            JAVMetadata.title_ko.isnot(None),
            JAVMetadata.title_ko.like(f"%{HARVEST_FAILED_TITLE_MARKER}%"),
        ),
    )


def _has_real_metadata_filter():
    return and_(
        JAVMetadata.title_ko.isnot(None),
        JAVMetadata.title_ko != "",
        or_(
            JAVMetadata.analysis_status.is_(None),
            JAVMetadata.analysis_status != "FAILED_CRAWL",
        ),
        or_(
            JAVMetadata.title_ko.is_(None),
            ~JAVMetadata.title_ko.like(f"%{HARVEST_FAILED_TITLE_MARKER}%"),
        ),
    )


def _without_metadata_filter():
    return or_(
        JAVMetadata.title_ko.is_(None),
        JAVMetadata.title_ko == "",
        JAVMetadata.analysis_status == "FAILED_CRAWL",
        JAVMetadata.title_ko.like(f"%{HARVEST_FAILED_TITLE_MARKER}%"),
    )


def _default_list_filter():
    """기본 목록: 수집 실패 placeholder만 제외 (title_ko NULL은 NOT LIKE에서 빠지지 않게)."""
    has_title = and_(JAVMetadata.title_ko.isnot(None), JAVMetadata.title_ko != "")
    return or_(
        ~has_title,
        and_(
            or_(
                JAVMetadata.analysis_status.is_(None),
                JAVMetadata.analysis_status != "FAILED_CRAWL",
            ),
            ~JAVMetadata.title_ko.like(f"%{HARVEST_FAILED_TITLE_MARKER}%"),
        ),
    )


def _has_folder_filter():
    return and_(
        JAVMetadata.folder_path.isnot(None),
        JAVMetadata.folder_path != "",
    )


def _no_folder_filter():
    return or_(
        JAVMetadata.folder_path.is_(None),
        JAVMetadata.folder_path == "",
    )


def _path_self_subtitle_sql(column):
    return or_(
        column.like("%자체자막%"),
        column.like("%자체%자막%"),
    )


def _path_mosaic_sql(column):
    return or_(
        column.ilike("%모자이크%삭제%"),
        column.ilike("%모자이크%제거%"),
        column.ilike("%모자이크%파괴%"),
        column.ilike("%uncen%"),
        column.ilike("%uncensored%"),
        column.ilike("%reducing%mosaic%"),
    )


def _subtitle_filter():
    """자막(.ko.srt/.srt) 또는 자체자막."""
    return or_(
        JAVMetadata.is_hardcoded.is_(True),
        FileFlagCache.lamp_sub == 1,
        _path_self_subtitle_sql(JAVMetadata.folder_path),
        _path_self_subtitle_sql(FileFlagCache.video_path),
    )


def _no_ko_or_hardcoded_subtitle():
    """KO/일반 SRT·자체자막이 없는 조건 (JA 유무는 별도)."""
    folder = func.coalesce(JAVMetadata.folder_path, "")
    video = func.coalesce(FileFlagCache.video_path, "")
    return and_(
        or_(JAVMetadata.is_hardcoded.is_(False), JAVMetadata.is_hardcoded.is_(None)),
        or_(FileFlagCache.lamp_sub.is_(None), FileFlagCache.lamp_sub != 1),
        ~folder.like("%자체자막%"),
        ~folder.like("%자체%자막%"),
        ~video.like("%자체자막%"),
        ~video.like("%자체%자막%"),
    )


def _no_subtitle_filter():
    """자막·자체자막·일본어 자막이 모두 없는 작품."""
    return and_(
        _no_ko_or_hardcoded_subtitle(),
        or_(FileFlagCache.lamp_stt.is_(None), FileFlagCache.lamp_stt != 1),
    )


def _ja_only_subtitle_filter():
    """일본어 자막(.ja.srt)만 있고 KO/자체자막은 없음."""
    return and_(
        FileFlagCache.lamp_stt == 1,
        _no_ko_or_hardcoded_subtitle(),
    )


def _normalize_subtitle_filter(
    subtitle_filter: Optional[str] = None,
    has_subtitle: Optional[bool] = None,
) -> Optional[str]:
    """'has' | 'none' | 'ja_only' | None(전체). 레거시 has_subtitle bool 호환."""
    raw = (subtitle_filter or "").strip().lower()
    if raw in ("has", "none", "ja_only"):
        return raw
    if raw in ("", "all"):
        if has_subtitle is True:
            return "has"
        if has_subtitle is False:
            return "none"
        return None
    if has_subtitle is True:
        return "has"
    if has_subtitle is False:
        return "none"
    return None


def _apply_subtitle_filter(query, mode: Optional[str]):
    if mode == "has":
        return query.filter(_subtitle_filter())
    if mode == "none":
        return query.filter(_no_subtitle_filter())
    if mode == "ja_only":
        return query.filter(_ja_only_subtitle_filter())
    return query


def _mosaic_removed_filter():
    """모자이크 제거(모파) 작품."""
    return or_(
        JAVMetadata.is_mopa.is_(True),
        _path_mosaic_sql(JAVMetadata.folder_path),
        _path_mosaic_sql(FileFlagCache.video_path),
    )


def _user_liked_exists():
    return exists().where(
        and_(
            WatchHistory.product_code == JAVMetadata.product_code,
            WatchHistory.liked.is_(True),
        )
    ).correlate(JAVMetadata)


def _watch_later_exists():
    return exists().where(
        and_(
            WatchHistory.product_code == JAVMetadata.product_code,
            WatchHistory.watch_later.is_(True),
        )
    ).correlate(JAVMetadata)


def is_safe_image_path(p: Path) -> bool:
    try:
        resolved = p.resolve()
        return any(resolved.is_relative_to(root) for root in _SAFE_IMAGE_ROOTS)
    except (OSError, ValueError):
        return False


def _is_subtitle_srt_file(name: str) -> bool:
    n = (name or "").lower()
    return n.endswith(".ko.srt") or (n.endswith(".srt") and not n.endswith(".ja.srt"))


def _sidecar_has_subtitle(video_path: Path) -> bool:
    stem = str(video_path.with_suffix(""))
    return Path(stem + ".ko.srt").is_file() or Path(stem + ".srt").is_file()


def _folder_has_subtitle_srt(folder_path: str, product_code: str, video_path: Path | None) -> bool:
    vp = video_path
    if vp is None or not vp.is_file():
        try:
            from javstory.library.video_discovery import guess_video_path_for_product_fast

            vp = guess_video_path_for_product_fast(product_code, folder_path)
        except Exception:
            vp = None
    if vp and vp.is_file() and _sidecar_has_subtitle(vp):
        return True
    root = Path(folder_path)
    if not root.is_dir():
        return False
    try:
        for p in root.rglob("*"):
            if p.is_file() and _is_subtitle_srt_file(p.name):
                return True
    except OSError:
        pass
    return False


def _preview_media_for(cache: dict[str, Any] | None) -> str | None:
    """목록용 미디어 종류. 캐시는 .webp 경로를 넣어도 실제 파일은 mp4일 수 있음."""
    if not cache:
        return None
    raw = (cache.get("preview_path") or "").strip()
    if not raw:
        return None
    try:
        from javstory.library.highlight.video_preview import resolve_preview_media_type

        return resolve_preview_media_type(Path(raw))
    except OSError:
        return None


def _preview_available(cache: dict[str, Any] | None) -> bool:
    """목록용 — preview_path 가 있고 실제 미디어가 해석되면 True.

    경로 문자열만 믿으면 stale 캐시로 호버만 되고 재생 실패한다.
    """
    return _preview_media_for(cache) is not None


class LibraryService:
    def _grok_story_cache(self, product_code: str) -> dict[str, Any] | None:
        """Grok 스토리 JSON — `data/cache/story_context/` 및 `Transcription/story_context_cache/`."""
        pc = (product_code or "").strip().upper()
        if not pc:
            return None
        try:
            from javstory.config.app_config import library_story_context_batch_tier
            from javstory.translation.story_grok_module import load_cached_grok_json_flexible

            data = load_cached_grok_json_flexible(pc, library_story_context_batch_tier())
            return data if isinstance(data, dict) and data else None
        except Exception:
            return None

    @staticmethod
    def _grok_scenes_from_data(grok: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, sc in enumerate(grok.get("scenes") or []):
            if not isinstance(sc, dict):
                continue
            summary = str(sc.get("scene_summary") or "").strip()
            label = str(sc.get("scene_label") or "").strip()
            time_range = str(sc.get("time_range") or "").strip()
            if not (summary or label or time_range):
                continue
            tags_raw = sc.get("key_tags") or []
            key_tags = [
                str(t).strip()
                for t in tags_raw
                if isinstance(t, str) and str(t).strip()
            ] if isinstance(tags_raw, list) else []
            out.append(
                {
                    "scene_id": str(sc.get("scene_id") or f"S{i + 1:02d}"),
                    "time_range": time_range,
                    "scene_label": label,
                    "scene_summary": summary,
                    "tone": str(sc.get("tone") or "").strip(),
                    "key_tags": key_tags,
                }
            )
        return out

    def grok_scenes_for(self, product_code: str) -> list[dict[str, Any]]:
        grok = self._grok_story_cache(product_code)
        if not grok:
            return []
        return self._grok_scenes_from_data(grok)

    def canonical_scenes_for(self, product_code: str) -> list[dict[str, Any]]:
        pc = (product_code or "").strip().upper()
        if not pc:
            return []
        try:
            state = load_work(pc)
            if not state or not state.scenes:
                return []
            return [
                {
                    "scene_id": s.scene_id,
                    "time_range": s.time_range or "",
                    "scene_label": s.scene_label or "",
                    "scene_summary": s.scene_summary or "",
                    "tone": s.tone or "",
                    "key_tags": list(s.key_tags or []),
                }
                for s in state.scenes
            ]
        except Exception:
            return []

    def grok_summary_for(self, product_code: str) -> str:
        grok = self._grok_story_cache(product_code)
        if not grok:
            return ""
        return (
            str(grok.get("overall_summary") or grok.get("synopsis_short") or "").strip()
        )

    def list_items(
        self,
        *,
        q: str = "",
        page: int = 1,
        per_page: int = 40,
        sort: str = "updated_at",
        order: str = "desc",
        has_folder: Optional[bool] = None,
        has_metadata: Optional[bool] = None,
        has_subtitle: Optional[bool] = None,
        subtitle_filter: Optional[str] = None,
        has_mosaic_removed: Optional[bool] = None,
        user_liked: Optional[bool] = None,
        watch_later: Optional[bool] = None,
        genres: Optional[list[str]] = None,
        genre_mode: str = "and",
        include_total: bool = True,
    ) -> dict[str, Any]:
        sub_mode = _normalize_subtitle_filter(subtitle_filter, has_subtitle)
        if sub_mode is not None:
            try:
                from javstory.library.file_flag_scanner import schedule_lamp_flag_repair

                # 목록 응답을 막지 않음 — 캐시 수리는 백그라운드
                schedule_lamp_flag_repair(
                    need_sub=sub_mode in ("has", "none", "ja_only"),
                    need_stt=sub_mode in ("none", "ja_only"),
                )
            except Exception:
                pass

        with get_db_session_ctx() as db:
            query = db.query(JAVMetadata)

            if sub_mode is not None or has_mosaic_removed:
                query = query.outerjoin(
                    FileFlagCache,
                    JAVMetadata.product_code == FileFlagCache.product_code,
                )

            if q:
                term = f"%{q}%"
                query = query.filter(
                    or_(
                        JAVMetadata.product_code.ilike(term),
                        JAVMetadata.title_ko.ilike(term),
                        JAVMetadata.title_ja.ilike(term),
                        JAVMetadata.actors_ko.ilike(term),
                        JAVMetadata.actors_ja.ilike(term),
                    )
                )

            if has_folder is True:
                query = query.filter(_has_folder_filter())
            elif has_folder is False:
                query = query.filter(_no_folder_filter())

            if has_metadata is True:
                query = query.filter(_has_real_metadata_filter())
            elif has_metadata is False:
                query = query.filter(_without_metadata_filter())
            else:
                query = query.filter(_default_list_filter())

            query = _apply_subtitle_filter(query, sub_mode)
            if has_mosaic_removed:
                query = query.filter(_mosaic_removed_filter())
            if user_liked is True:
                query = query.filter(_user_liked_exists())
            elif user_liked is False:
                query = query.filter(~_user_liked_exists())
            if watch_later is True:
                query = query.filter(_watch_later_exists())
            elif watch_later is False:
                query = query.filter(~_watch_later_exists())

            query = apply_genre_filters(query, genres, mode=genre_mode)

            total = query.count() if include_total else 0
            if watch_later is True and sort == "updated_at":
                # EXISTS와 동일 엔티티 JOIN 시 auto-correlation 깨짐 → alias 사용
                wh_sort = aliased(WatchHistory)
                query = query.outerjoin(
                    wh_sort,
                    and_(
                        wh_sort.product_code == JAVMetadata.product_code,
                        wh_sort.watch_later.is_(True),
                    ),
                ).order_by(
                    wh_sort.watch_later_added_at.desc()
                    if order == "desc"
                    else wh_sort.watch_later_added_at.asc()
                )
            else:
                sort_key = sort if sort in _SORT_COLS else "updated_at"
                sort_col = _SORT_COLS[sort_key]
                query = query.order_by(
                    sort_col.desc() if order == "desc" else sort_col.asc()
                )
            rows = query.offset((page - 1) * per_page).limit(per_page).all()

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "items": rows,
            }

    def search_items(
        self,
        *,
        q: str = "",
        mode: str = "auto",
        page: int = 1,
        per_page: int = 40,
        sort: str = "updated_at",
        order: str = "desc",
        has_folder: Optional[bool] = None,
        has_metadata: Optional[bool] = None,
        has_subtitle: Optional[bool] = None,
        subtitle_filter: Optional[str] = None,
        has_mosaic_removed: Optional[bool] = None,
        user_liked: Optional[bool] = None,
        watch_later: Optional[bool] = None,
        genres: Optional[list[str]] = None,
        genre_mode: str = "and",
    ) -> dict[str, Any]:
        """Keyword ILIKE or hybrid (BM25+embedding+RRF) search with LibraryItem hydration."""
        from javstory.library.embeddings.pipeline import embeddings_enabled_from_env
        from javstory.search.library_search import HybridLibrarySearch

        term = (q or "").strip()
        mode_norm = (mode or "auto").strip().lower()
        if mode_norm not in ("keyword", "hybrid", "auto"):
            mode_norm = "auto"

        use_hybrid = mode_norm == "hybrid" or (
            mode_norm == "auto" and self._looks_like_natural_language(term)
        )
        embeddings_on = embeddings_enabled_from_env()

        if not term or not use_hybrid:
            result = self.list_items(
                q=term,
                page=page,
                per_page=per_page,
                sort=sort,
                order=order,
                has_folder=has_folder,
                has_metadata=has_metadata,
                has_subtitle=has_subtitle,
                subtitle_filter=subtitle_filter,
                has_mosaic_removed=has_mosaic_removed,
                user_liked=user_liked,
                watch_later=watch_later,
                genres=genres,
                genre_mode=genre_mode,
                include_total=True,
            )
            return {
                **result,
                "mode": "keyword",
                "embeddings_enabled": embeddings_on,
                "embedding_channel_used": False,
                "search_message": None,
                "hit_meta": {},
            }

        # 자연어/하이브리드 UI 경로는 임베딩 히트만 사용 (BM25·메타 혼합·건수 고정 없음).
        searcher = HybridLibrarySearch()
        hits = searcher.search_by_embedding(term)
        emb_diag = dict(getattr(searcher, "last_embedding_diag", None) or {})
        hit_meta = {
            str(h.get("id") or "").strip().upper(): {
                "score": float(h.get("score") or 0),
                "source": "embedding",
            }
            for h in hits
            if str(h.get("id") or "").strip()
        }
        ranked_codes = [c for c in hit_meta.keys()]
        embedding_used = bool(ranked_codes) and str(emb_diag.get("status") or "") == "ok"

        if not ranked_codes:
            msg = "검색 결과가 없습니다."
            if not embeddings_on:
                msg = "임베딩이 꺼져 있어 시맨틱 검색을 할 수 없습니다. 설정에서 임베딩을 켜 주세요."
            else:
                err = str(emb_diag.get("error") or "")
                status = str(emb_diag.get("status") or "")
                if status == "query_failed" and (
                    "ConnectError" in err or "connection" in err.lower() or "ConnectTimeout" in err
                ):
                    msg = (
                        "Ollama에 연결할 수 없어 시맨틱 검색을 할 수 없습니다. "
                        "Ollama 앱을 실행하거나 `ollama serve` 후 다시 검색하세요 "
                        f"(URL: {(emb_diag.get('url') or 'http://localhost:11434')})."
                    )
                elif status == "query_failed":
                    msg = (
                        "검색어 임베딩에 실패했습니다. "
                        f"Ollama 모델({emb_diag.get('model') or 'embeddings'})과 로그를 확인하세요."
                    )
                elif int(emb_diag.get("scored_n") or 0) == 0:
                    msg = (
                        "임베딩 캐시가 없어 시맨틱 검색 결과가 없습니다. "
                        "설정에서 임베딩 워밍업을 실행해 보세요."
                    )
                elif int(emb_diag.get("scored_n") or 0) > 0:
                    msg = (
                        "유사도가 충분히 높은 작품이 없습니다. "
                        "검색어를 바꾸거나 임베딩 워밍업·모델 설정을 확인해 보세요."
                    )
            return {
                "total": 0,
                "page": page,
                "per_page": per_page,
                "items": [],
                "mode": "hybrid",
                "embeddings_enabled": embeddings_on,
                "embedding_channel_used": False,
                "search_message": msg,
                "hit_meta": {},
            }

        with get_db_session_ctx() as db:
            # 전체 행 로드 대신 코드만 필터 → 페이지 분량만 hydrate (다음 페이지 체감 개선)
            query = db.query(JAVMetadata.product_code).filter(
                JAVMetadata.product_code.in_(ranked_codes)
            )

            sub_mode = _normalize_subtitle_filter(subtitle_filter, has_subtitle)
            if sub_mode is not None:
                try:
                    from javstory.library.file_flag_scanner import schedule_lamp_flag_repair

                    schedule_lamp_flag_repair(
                        need_sub=sub_mode in ("has", "none", "ja_only"),
                        need_stt=sub_mode in ("none", "ja_only"),
                    )
                except Exception:
                    pass
            if sub_mode is not None or has_mosaic_removed:
                query = query.outerjoin(
                    FileFlagCache,
                    JAVMetadata.product_code == FileFlagCache.product_code,
                )

            if has_folder is True:
                query = query.filter(_has_folder_filter())
            elif has_folder is False:
                query = query.filter(_no_folder_filter())

            if has_metadata is True:
                query = query.filter(_has_real_metadata_filter())
            elif has_metadata is False:
                query = query.filter(_without_metadata_filter())
            else:
                query = query.filter(_default_list_filter())

            query = _apply_subtitle_filter(query, sub_mode)
            if has_mosaic_removed:
                query = query.filter(_mosaic_removed_filter())
            if user_liked is True:
                query = query.filter(_user_liked_exists())
            elif user_liked is False:
                query = query.filter(~_user_liked_exists())
            if watch_later is True:
                query = query.filter(_watch_later_exists())
            elif watch_later is False:
                query = query.filter(~_watch_later_exists())

            query = apply_genre_filters(query, genres, mode=genre_mode)
            filtered_codes = {
                str(pc or "").strip().upper()
                for (pc,) in query.all()
                if str(pc or "").strip()
            }
            sort_norm = (sort or "updated_at").strip().lower()
            if sort_norm in ("similarity", "relevance", "score", "embedding"):
                ordered_codes = [c for c in ranked_codes if c in filtered_codes]
                if order == "asc":
                    ordered_codes = list(reversed(ordered_codes))
            else:
                sort_col = _SORT_COLS.get(sort_norm, JAVMetadata.updated_at)
                ranked_rows = (
                    db.query(JAVMetadata.product_code)
                    .filter(JAVMetadata.product_code.in_(list(filtered_codes)))
                    .order_by(sort_col.desc() if order == "desc" else sort_col.asc())
                    .all()
                )
                ordered_codes = [
                    str(pc or "").strip().upper()
                    for (pc,) in ranked_rows
                    if str(pc or "").strip()
                ]
            total = len(ordered_codes)
            start = max(0, (page - 1) * per_page)
            page_codes = ordered_codes[start : start + per_page]
            if not page_codes:
                page_rows = []
            else:
                rows = (
                    db.query(JAVMetadata)
                    .filter(JAVMetadata.product_code.in_(page_codes))
                    .all()
                )
                by_code = {
                    str(r.product_code or "").strip().upper(): r
                    for r in rows
                    if str(r.product_code or "").strip()
                }
                page_rows = [by_code[c] for c in page_codes if c in by_code]

        message = None
        if not embedding_used:
            message = (
                "시맨틱 채널이 결과에 반영되지 않았습니다. "
                "설정에서 임베딩 워밍업을 실행해 보세요."
            )

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "items": page_rows,
            "mode": "hybrid",
            "embeddings_enabled": embeddings_on,
            "embedding_channel_used": embedding_used,
            "search_message": message,
            "hit_meta": hit_meta,
        }

    @staticmethod
    def _looks_like_natural_language(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if re.search(r"\s", t):
            return True
        if re.match(r"^[A-Za-z]{1,10}-?\d{2,6}[A-Za-z0-9\-]*$", t):
            return False
        if re.search(r"[가-힣]{4,}", t):
            return True
        return len(t) >= 12 and not re.match(r"^[A-Za-z0-9\-_.]+$", t)

    def stats(self) -> dict[str, int]:
        global _STATS_CACHE
        now = time.time()
        if _STATS_CACHE and (now - _STATS_CACHE[0]) < _STATS_CACHE_TTL_SEC:
            return dict(_STATS_CACHE[1])

        with get_db_session_ctx() as db:
            total, with_metadata, with_folder = db.query(
                func.count(JAVMetadata.id),
                func.sum(case((_has_real_metadata_filter(), 1), else_=0)),
                func.sum(case((_has_folder_filter(), 1), else_=0)),
            ).one()
            total = int(total or 0)
            with_metadata = int(with_metadata or 0)
            with_folder = int(with_folder or 0)
            result = {
                "total": total,
                "with_metadata": with_metadata,
                "with_folder": with_folder,
                "without_metadata": total - with_metadata,
            }

        _STATS_CACHE = (now, result)
        return dict(result)

    def list_genres(self, *, limit: int = 200, force_refresh: bool = False) -> list[dict[str, Any]]:
        global _GENRES_CACHE
        now = time.time()
        if (
            not force_refresh
            and _GENRES_CACHE
            and (now - _GENRES_CACHE[0]) < _GENRES_CACHE_TTL_SEC
        ):
            return list(_GENRES_CACHE[1])

        with get_db_session_ctx() as db:
            rows = (
                db.query(JAVMetadata.genres_ko, JAVMetadata.genres)
                .filter(
                    or_(
                        and_(
                            JAVMetadata.genres_ko.isnot(None),
                            JAVMetadata.genres_ko != "",
                        ),
                        and_(
                            JAVMetadata.genres.isnot(None),
                            JAVMetadata.genres != "",
                        ),
                    )
                )
                .all()
            )
        raw_values = [(r[0] or r[1]) for r in rows]
        items = aggregate_genre_counts(raw_values, limit=limit)
        _GENRES_CACHE = (now, items)
        return items

    def get_by_code(self, code: str) -> Optional[JAVMetadata]:
        with get_db_session_ctx() as db:
            return db.query(JAVMetadata).filter_by(product_code=code.upper()).first()

    def load_file_flags_for(self, product_codes: list[str]) -> dict[str, dict[str, Any]]:
        if not product_codes:
            return {}
        from javstory.library.file_flag_scanner import load_flags_for_codes

        with get_db_session_ctx() as db:
            return load_flags_for_codes(db, product_codes)

    def load_watch_flags_for(self, product_codes: list[str]) -> dict[str, dict[str, Any]]:
        codes = [str(c or "").strip().upper() for c in product_codes if str(c or "").strip()]
        if not codes:
            return {}
        out: dict[str, dict[str, Any]] = {
            pc: {"user_liked": False, "watch_later": False} for pc in codes
        }
        with get_db_session_ctx() as db:
            rows = (
                db.query(WatchHistory)
                .filter(WatchHistory.product_code.in_(list(out.keys())))
                .all()
            )
            for h in rows:
                pc = str(h.product_code or "").strip().upper()
                if not pc:
                    continue
                out[pc] = {
                    "user_liked": bool(h.liked),
                    "watch_later": bool(getattr(h, "watch_later", False)),
                }
        return out

    def toggle_user_like(self, product_code: str) -> dict[str, Any]:
        import datetime as _dt

        pc = (product_code or "").strip().upper()
        if not pc:
            return {"ok": False, "user_liked": False, "watch_later": False}
        now = _dt.datetime.now()
        with get_db_session_ctx() as db:
            history = db.query(WatchHistory).filter_by(product_code=pc).first()
            if not history:
                history = WatchHistory(product_code=pc, created_at=now)
                db.add(history)
            new_liked = not bool(history.liked)
            history.liked = new_liked
            history.disliked = False
            history.updated_at = now
            watch_later = bool(getattr(history, "watch_later", False))
            db.commit()
        try:
            from javstory.analytics.preference_engine import score_preferences

            score_preferences(pc, delta=3 if new_liked else -3)
        except Exception:
            pass
        return {"ok": True, "user_liked": new_liked, "watch_later": watch_later}

    def toggle_watch_later(self, product_code: str) -> dict[str, Any]:
        import datetime as _dt

        pc = (product_code or "").strip().upper()
        if not pc:
            return {"ok": False, "user_liked": False, "watch_later": False}
        now = _dt.datetime.now()
        with get_db_session_ctx() as db:
            history = db.query(WatchHistory).filter_by(product_code=pc).first()
            if not history:
                history = WatchHistory(product_code=pc, created_at=now)
                db.add(history)
            new_value = not bool(getattr(history, "watch_later", False))
            history.watch_later = new_value
            history.watch_later_added_at = now if new_value else None
            history.updated_at = now
            liked = bool(history.liked)
            db.commit()
        return {"ok": True, "user_liked": liked, "watch_later": new_value}

    def media_flags_for(
        self, row: JAVMetadata, cache: dict[str, Any] | None = None
    ) -> dict[str, bool]:
        pc = (row.product_code or "").strip().upper()
        folder = (row.folder_path or "").strip() or None
        trust_cache = cache is not None

        video_path: Path | None = None
        if cache and cache.get("video_path"):
            try:
                video_path = Path(cache["video_path"])
            except Exception:
                video_path = None

        # 목록 하이드레이션(캐시 있음)에서는 디스크 경로 추측을 하지 않는다
        if video_path is None and folder and not trust_cache:
            try:
                from javstory.library.video_discovery import guess_video_path_for_product_fast

                video_path = guess_video_path_for_product_fast(pc, folder)
            except Exception:
                video_path = None

        hardcoded = bool(row.is_hardcoded)
        if not hardcoded:
            hardcoded = path_contains_self_subtitle_marker(video_path, folder, pc)

        mosaic_removed = bool(row.is_mopa)
        if not mosaic_removed:
            mosaic_removed = path_contains_mopa_marker(video_path, folder)

        has_subtitle = False
        if not hardcoded:
            if trust_cache:
                # FileFlagCache 를 신뢰 — lamp_sub=0 일 때 폴더 rglob 하지 않음
                has_subtitle = bool(int(cache.get("lamp_sub") or 0))
            elif folder:
                has_subtitle = _folder_has_subtitle_srt(folder, pc, video_path)

        return {
            "has_subtitle": has_subtitle,
            "has_hardcoded_subtitle": hardcoded,
            "has_mosaic_removed": mosaic_removed,
            "has_preview": _preview_available(cache),
            "preview_media": _preview_media_for(cache),
        }

    def scene_count_for(self, product_code: str) -> int:
        grok_scenes = self.grok_scenes_for(product_code)
        if grok_scenes:
            return len(grok_scenes)
        pc = (product_code or "").strip().upper()
        if not pc:
            return 0
        try:
            state = load_work(pc)
            return len(state.scenes) if state and state.scenes else 0
        except Exception:
            return 0

    def scene_counts_for(
        self,
        product_codes: list[str],
        flags_map: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """목록 API용 배치 씬 수 — grok 캐시(has_story)만 읽고 나머지는 0."""
        flags_map = flags_map or {}
        out: dict[str, int] = {}
        for raw in product_codes:
            pc = (raw or "").strip().upper()
            if not pc:
                continue
            out[pc] = 0
            cache = flags_map.get(pc) or flags_map.get(raw) or {}
            if not int(cache.get("has_story") or 0):
                continue
            grok = self._grok_story_cache(pc)
            if not grok:
                continue
            scenes = grok.get("scenes")
            if isinstance(scenes, list):
                out[pc] = len(scenes)
        return out

    def scenes_for(self, product_code: str) -> list[dict[str, Any]]:
        grok_scenes = self.grok_scenes_for(product_code)
        if grok_scenes:
            return grok_scenes
        return self.canonical_scenes_for(product_code)

    def canonical_summary_for(self, product_code: str) -> str:
        grok_summary = self.grok_summary_for(product_code)
        if grok_summary:
            return grok_summary
        pc = (product_code or "").strip().upper()
        if not pc:
            return ""
        try:
            state = load_work(pc)
            return (state.overall_summary or "").strip() if state else ""
        except Exception:
            return ""

    def resolve_cover_path(self, code: str) -> Optional[Path]:
        row = self.get_by_code(code)
        if not row:
            return None
        for path_field in (row.cover_image_local_path, row.thumb_image_local_path):
            if not path_field:
                continue
            p = Path(path_field)
            if is_safe_image_path(p) and p.is_file():
                return p
        return None

    def resolve_preview_path(self, code: str) -> Optional[Path]:
        from javstory.library.file_flag_scanner import resolve_preview_path as lookup_preview

        pc = (code or "").strip().upper()
        if not pc:
            return None
        cached = lookup_preview(pc)
        if not cached:
            flags = self.load_file_flags_for([pc]).get(pc, {})
            cached = flags.get("preview_path")
        if not cached:
            return None
        p = Path(cached)
        mp4 = p.with_suffix(".mp4")
        if mp4.is_file() and is_safe_image_path(mp4):
            return mp4
        if is_safe_image_path(p) and p.is_file():
            return p
        return None

    def open_folder(self, product_code: str) -> dict[str, Any]:
        import os

        from javstory.library.paths import work_library_dir

        pc = (product_code or "").strip().upper()
        if not pc:
            return {"ok": False, "message": "품번이 필요합니다."}

        row = self.get_by_code(pc)
        folder_to_open: Path | None = None

        if row and row.folder_path:
            p = Path(row.folder_path)
            if p.exists():
                folder_to_open = p

        if not folder_to_open:
            d = work_library_dir(pc)
            if d.is_dir():
                folder_to_open = d

        if not folder_to_open:
            return {"ok": False, "message": "저장된 폴더 위치를 찾을 수 없습니다."}

        os.startfile(folder_to_open)
        return {"ok": True, "path": str(folder_to_open)}

    def set_cover_from_file(self, product_code: str, source_path: str | Path) -> dict[str, Any]:
        from javstory.library.cover_upload import persist_cover_paths, save_cover_image

        pc = (product_code or "").strip().upper()
        try:
            poster = save_cover_image(pc, source_path)
            local = persist_cover_paths(pc, poster)
            return {"ok": True, "path": local}
        except ValueError as e:
            return {"ok": False, "message": str(e)}
        except OSError as e:
            return {"ok": False, "message": f"표지 저장 실패: {e}"}

    async def fetch_cover_from_url(self, product_code: str) -> dict[str, Any]:
        from javstory.library.cover_upload import persist_cover_paths
        from javstory.utils.assets_handler import MetadataAssetsHandler

        pc = (product_code or "").strip().upper()
        row = self.get_by_code(pc)
        if not row:
            return {"ok": False, "message": "작품을 찾을 수 없습니다."}
        url = (row.cover_image_url or "").strip()
        if not url or url == "이미지 누락":
            return {"ok": False, "message": "저장된 표지 URL이 없습니다."}

        path = await MetadataAssetsHandler().download_cover_image(url, pc)
        if not path:
            return {"ok": False, "message": "표지 다운로드에 실패했습니다."}

        try:
            local = persist_cover_paths(pc, path)
            return {"ok": True, "path": local}
        except ValueError as e:
            return {"ok": False, "message": str(e)}

    def update_item(self, code: str, data: dict[str, Any]) -> Optional[JAVMetadata]:
        from javstory.harvest.database import commit_with_retry
        from javstory.library.detail_persist import persist_metadata_row_and_sync_files
        from javstory.library.metadata_edit import (
            apply_library_metadata_fields,
            mark_metadata_as_manual,
        )

        pc = (code or "").strip().upper()
        if not pc:
            return None
        with get_db_session_ctx() as db:
            row = db.query(JAVMetadata).filter_by(product_code=pc).first()
            if not row:
                return None
            apply_library_metadata_fields(row, data)
            mark_metadata_as_manual(row)
            commit_with_retry(db)
            db.refresh(row)
            persist_metadata_row_and_sync_files(pc, row)
            return row

    def bind_folder(
        self,
        product_code: str,
        folder_path: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        from javstory.harvest.database import commit_with_retry
        from javstory.harvest.product_repository import (
            resolve_video_paths_for_playback,
            set_folder_path,
            sync_media_bundle,
            sync_product_from_metadata_row,
        )
        from javstory.library.video_discovery import first_video_in_dir
        from javstory.utils.product_code import extract_product_code_from_path

        pc = (product_code or "").strip().upper()
        target_path = Path((folder_path or "").strip())
        if not pc:
            return {"ok": False, "message": "품번이 필요합니다."}
        if not target_path.is_dir():
            return {"ok": False, "message": f"폴더가 없거나 디렉터리가 아닙니다: {folder_path}"}

        detected_pc = extract_product_code_from_path(target_path)
        if not detected_pc:
            video = first_video_in_dir(target_path)
            if video:
                detected_pc = extract_product_code_from_path(video)

        mismatch = not detected_pc or detected_pc.upper() != pc
        if mismatch and not force:
            return {
                "ok": False,
                "message": (
                    f"선택한 폴더({target_path.name})가 품번 {pc}와 일치하지 않습니다. "
                    "강제 연결을 사용하세요."
                ),
                "mismatch": True,
            }

        with get_db_session_ctx() as db:
            row = db.query(JAVMetadata).filter_by(product_code=pc).first()
            if not row:
                return {"ok": False, "message": f"DB에 품번 {pc} 메타데이터가 없습니다."}

            abs_path = str(target_path.resolve())
            set_folder_path(db, pc, abs_path)
            try:
                video = first_video_in_dir(target_path)
                row.is_hardcoded = bool(
                    path_contains_self_subtitle_marker(video, abs_path, pc)
                )
                row.is_mopa = bool(path_contains_mopa_marker(video, abs_path))
            except Exception:
                pass
            sync_product_from_metadata_row(db, row)
            commit_with_retry(db)
            db.refresh(row)

            try:
                video_paths = resolve_video_paths_for_playback(pc, abs_path)
                if video_paths:
                    sync_media_bundle(pc, abs_path, video_paths)
            except Exception:
                pass

            return {
                "ok": True,
                "path": abs_path,
                "forced": bool(mismatch and force),
                "row": row,
            }

    def clear_folder_binding(self, product_code: str) -> dict[str, Any]:
        from javstory.harvest.database import commit_with_retry
        from javstory.harvest.product_repository import (
            clear_video_files_for_product,
            set_folder_path,
            sync_product_from_metadata_row,
        )

        pc = (product_code or "").strip().upper()
        if not pc:
            return {"ok": False, "message": "품번이 필요합니다."}

        with get_db_session_ctx() as db:
            row = db.query(JAVMetadata).filter_by(product_code=pc).first()
            if not row:
                return {"ok": False, "message": f"DB에 품번 {pc}가 없습니다."}

            set_folder_path(db, pc, None)
            sync_product_from_metadata_row(db, row)
            clear_video_files_for_product(db, pc)
            commit_with_retry(db)
            db.refresh(row)
            return {"ok": True, "row": row}

    def snapshot_paths_for(self, product_code: str) -> list[Path]:
        pc = (product_code or "").strip().upper()
        if not pc:
            return []
        row = self.get_by_code(pc)
        folder = (row.folder_path or "").strip() if row else ""
        return discover_snapshot_paths(pc, folder_path=folder or None)

    def snapshot_count_for(self, product_code: str) -> int:
        return len(self.snapshot_paths_for(product_code))

    def resolve_snapshot_path(self, product_code: str, index: int) -> Optional[Path]:
        paths = self.snapshot_paths_for(product_code)
        if index < 0 or index >= len(paths):
            return None
        p = paths[index]
        if not p.is_file() or not is_safe_image_path(p):
            return None
        return p
