from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from javstory.harvest.database import JAVMetadata
from javstory.services.library_service import LibraryService
from webapi.schemas import (
    CoverUploadResponse,
    EmbeddingsWarmupResponse,
    FolderBindRequest,
    FolderBindResponse,
    GrokStoryStartRequest,
    GrokStoryStartResponse,
    LibraryItem,
    LibraryItemDetail,
    LibraryItemUpdate,
    LibraryListResponse,
    LibraryGenreItem,
    LibraryStats,
    OpenFolderResponse,
    SceneSummary,
    WatchFlagsResponse,
)

router = APIRouter()
_library = LibraryService()


def _folder_watch_flags(code: str) -> dict[str, bool]:
    from javstory.folder_watch.inbox import inbox_contains
    from javstory.folder_watch.paused import is_monitoring_paused

    pc = (code or "").strip().upper()
    if not pc:
        return {"folder_monitoring_paused": False, "folder_binding_pending": False}
    return {
        "folder_monitoring_paused": is_monitoring_paused(pc),
        "folder_binding_pending": inbox_contains(pc),
    }


def _after_folder_binding_change(code: str) -> None:
    from javstory.folder_watch.inbox import remove_inbox_item
    from javstory.folder_watch.service import get_folder_watch_service

    pc = code.strip().upper()
    remove_inbox_item(pc)
    svc = get_folder_watch_service()
    svc.clear_broken_flag(pc)
    svc.refresh_paths_from_db()
    svc.notify_change()


def _to_item(
    row: JAVMetadata,
    cache: dict | None = None,
    scene_counts: dict[str, int] | None = None,
    *,
    search_score: float | None = None,
    search_source: str | None = None,
    watch_flags: dict | None = None,
) -> LibraryItem:
    base = LibraryItem.model_validate(row)
    fav = int(getattr(row, "favorite_score", 0) or 0)
    pc = (row.product_code or "").strip().upper()
    count = (scene_counts or {}).get(pc, 0)
    media = _library.media_flags_for(row, cache)
    wf = watch_flags or {}
    update: dict = {
        "scene_count": count,
        "favorite_score": fav,
        "has_subtitle": media["has_subtitle"],
        "has_hardcoded_subtitle": media["has_hardcoded_subtitle"],
        "has_mosaic_removed": media["has_mosaic_removed"],
        "has_preview": media["has_preview"],
        "preview_media": media["preview_media"],
        "user_liked": bool(wf.get("user_liked")),
        "watch_later": bool(wf.get("watch_later")),
    }
    if search_score is not None:
        update["search_score"] = search_score
    if search_source:
        update["search_source"] = search_source
    return base.model_copy(update=update)


@router.get("", response_model=LibraryListResponse)
def list_library(
    q: str = Query("", description="검색어 (품번/제목/배우)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    sort: str = Query("updated_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    has_folder: Optional[bool] = None,
    has_metadata: Optional[bool] = None,
    has_subtitle: Optional[bool] = None,
    subtitle_filter: Optional[str] = Query(
        None,
        pattern="^(all|has|none|ja_only)$",
        description="자막 필터: all|has|none|ja_only",
    ),
    has_mosaic_removed: Optional[bool] = None,
    user_liked: Optional[bool] = None,
    watch_later: Optional[bool] = None,
    genres: str = Query("", description="쉼표 구분 장르 (genre_mode에 따라 AND/OR)"),
    genre_mode: str = Query("and", pattern="^(and|or)$", description="and=모두 포함, or=하나라도 포함"),
    include_total: bool = Query(True, description="false면 total 생략(append용)"),
):
    genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else None
    result = _library.list_items(
        q=q,
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
        genres=genre_list,
        genre_mode=genre_mode,
        include_total=include_total,
    )
    rows = result["items"]
    codes = [r.product_code for r in rows]
    flags_map = _library.load_file_flags_for(codes)
    watch_map = _library.load_watch_flags_for(codes)
    scene_counts = _library.scene_counts_for(codes, flags_map)
    return LibraryListResponse(
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        items=[
            _to_item(
                r,
                flags_map.get(r.product_code),
                scene_counts,
                watch_flags=watch_map.get((r.product_code or "").strip().upper()),
            )
            for r in rows
        ],
    )


@router.get("/search", response_model=LibraryListResponse)
def search_library(
    q: str = Query("", description="검색어 (키워드 또는 자연어)"),
    mode: str = Query("auto", pattern="^(auto|keyword|hybrid)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    sort: str = Query("updated_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    has_folder: Optional[bool] = None,
    has_metadata: Optional[bool] = None,
    has_subtitle: Optional[bool] = None,
    subtitle_filter: Optional[str] = Query(
        None,
        pattern="^(all|has|none|ja_only)$",
        description="자막 필터: all|has|none|ja_only",
    ),
    has_mosaic_removed: Optional[bool] = None,
    user_liked: Optional[bool] = None,
    watch_later: Optional[bool] = None,
    genres: str = Query("", description="쉼표 구분 장르"),
    genre_mode: str = Query("and", pattern="^(and|or)$"),
):
    genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else None
    result = _library.search_items(
        q=q,
        mode=mode,
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
        genres=genre_list,
        genre_mode=genre_mode,
    )
    rows = result["items"]
    codes = [r.product_code for r in rows]
    flags_map = _library.load_file_flags_for(codes)
    watch_map = _library.load_watch_flags_for(codes)
    scene_counts = _library.scene_counts_for(codes, flags_map)
    hit_meta = result.get("hit_meta") or {}
    items = []
    for r in rows:
        pc = (r.product_code or "").strip().upper()
        meta = hit_meta.get(pc) or {}
        items.append(
            _to_item(
                r,
                flags_map.get(r.product_code),
                scene_counts,
                search_score=meta.get("score"),
                search_source=meta.get("source") or None,
                watch_flags=watch_map.get(pc),
            )
        )
    return LibraryListResponse(
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        items=items,
        search_mode=result.get("mode"),
        embeddings_enabled=result.get("embeddings_enabled"),
        embedding_channel_used=result.get("embedding_channel_used"),
        search_message=result.get("search_message"),
    )


@router.post("/embeddings/warmup", response_model=EmbeddingsWarmupResponse)
def warmup_embeddings(max_batch: int = Query(12, ge=1, le=24)):
    from javstory.library.embeddings.web_status import start_embeddings_warmup

    return EmbeddingsWarmupResponse(**start_embeddings_warmup(max_batch=max_batch))


@router.post("/embeddings/backfill", response_model=EmbeddingsWarmupResponse)
def backfill_embeddings(batch_size: int = Query(4, ge=1, le=8)):
    from javstory.library.embeddings.web_status import start_embeddings_backfill

    return EmbeddingsWarmupResponse(**start_embeddings_backfill(batch_size=batch_size))


@router.post("/grok-story", response_model=GrokStoryStartResponse)
def start_grok_story_batch(body: GrokStoryStartRequest):
    from javstory.services.grok_story_service import start_grok_story_generation

    return GrokStoryStartResponse(
        **start_grok_story_generation(body.product_codes, force=bool(body.force))
    )


@router.post("/{code}/like", response_model=WatchFlagsResponse)
def toggle_library_like(code: str):
    row = _library.get_by_code(code)
    if not row:
        raise HTTPException(404, "작품을 찾을 수 없습니다")
    return WatchFlagsResponse(**_library.toggle_user_like(code))


@router.post("/{code}/watch-later", response_model=WatchFlagsResponse)
def toggle_library_watch_later(code: str):
    row = _library.get_by_code(code)
    if not row:
        raise HTTPException(404, "작품을 찾을 수 없습니다")
    return WatchFlagsResponse(**_library.toggle_watch_later(code))


@router.post("/{code}/grok-story", response_model=GrokStoryStartResponse)
def start_grok_story_one(code: str, force: bool = Query(False)):
    from javstory.services.grok_story_service import start_grok_story_generation

    row = _library.get_by_code(code)
    if not row:
        raise HTTPException(404, "작품을 찾을 수 없습니다")
    return GrokStoryStartResponse(
        **start_grok_story_generation([code], force=bool(force))
    )


@router.get("/stats", response_model=LibraryStats)
def library_stats():
    return LibraryStats(**_library.stats())


@router.get("/genres", response_model=list[LibraryGenreItem])
def library_genres(
    limit: int = Query(200, ge=1, le=500),
    force: bool = Query(False, description="캐시 무시 재조회"),
):
    return [LibraryGenreItem(**row) for row in _library.list_genres(limit=limit, force_refresh=force)]


@router.get("/cover/{code}")
def get_cover(code: str):
    path = _library.resolve_cover_path(code)
    if not path:
        raise HTTPException(404, "표지 이미지가 없습니다")
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/preview/{code}")
def get_preview(code: str):
    path = _library.resolve_preview_path(code)
    if not path:
        raise HTTPException(404, "프리뷰가 없습니다")
    return FileResponse(
        str(path),
        media_type="video/mp4" if path.suffix.lower() == ".mp4" else "image/webp",
        content_disposition_type="inline",
        headers={
            "Cache-Control": "no-cache",
            "Accept-Ranges": "bytes",
        },
    )


def _guess_image_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".png",):
        return "image/png"
    if ext in (".webp",):
        return "image/webp"
    return "image/jpeg"


@router.get("/{code}/snapshots/{index}")
def get_snapshot(code: str, index: int):
    if index < 0:
        raise HTTPException(400, "잘못된 스냅샷 인덱스입니다")
    path = _library.resolve_snapshot_path(code, index)
    if not path:
        raise HTTPException(404, "스냅샷을 찾을 수 없습니다")
    return FileResponse(str(path), media_type=_guess_image_mime(path))


@router.post("/{code}/open-folder", response_model=OpenFolderResponse)
def open_folder(code: str):
    result = _library.open_folder(code)
    if not result.get("ok"):
        raise HTTPException(404, result.get("message") or "폴더를 열 수 없습니다")
    return OpenFolderResponse(**result)


@router.post("/{code}/folder", response_model=FolderBindResponse)
def bind_folder(code: str, body: FolderBindRequest):
    result = _library.bind_folder(code, body.folder_path, force=body.force)
    if not result.get("ok"):
        raise HTTPException(
            400 if result.get("mismatch") else 404,
            result.get("message") or "폴더 연결에 실패했습니다",
        )
    try:
        _after_folder_binding_change(code)
    except Exception:
        pass
    row = result.get("row")
    detail = _to_detail(row, code.upper()) if row else None
    return FolderBindResponse(
        ok=True,
        path=result.get("path"),
        detail=detail,
    )


@router.delete("/{code}/folder", response_model=FolderBindResponse)
def clear_folder_binding(code: str):
    result = _library.clear_folder_binding(code)
    if not result.get("ok"):
        raise HTTPException(404, result.get("message") or "폴더 연결 해제에 실패했습니다")
    try:
        _after_folder_binding_change(code)
    except Exception:
        pass
    row = result.get("row")
    detail = _to_detail(row, code.upper()) if row else None
    return FolderBindResponse(ok=True, detail=detail)


@router.post("/{code}/cover", response_model=CoverUploadResponse)
async def upload_cover(code: str, file: UploadFile = File(...)):
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = _library.set_cover_from_file(code, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not result.get("ok"):
        raise HTTPException(400, result.get("message") or "표지 저장에 실패했습니다")

    row = _library.get_by_code(code)
    detail = _to_detail(row, code.upper()) if row else None
    return CoverUploadResponse(ok=True, path=result.get("path"), detail=detail)


@router.post("/{code}/cover/fetch", response_model=CoverUploadResponse)
async def fetch_cover(code: str):
    result = await _library.fetch_cover_from_url(code)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message") or "표지 다운로드에 실패했습니다")

    row = _library.get_by_code(code)
    detail = _to_detail(row, code.upper()) if row else None
    return CoverUploadResponse(ok=True, path=result.get("path"), detail=detail)


def _to_detail(row: JAVMetadata, code: str) -> LibraryItemDetail:
    base = LibraryItemDetail.model_validate(row)
    grok_scenes = _library.grok_scenes_for(code)
    scenes = grok_scenes if grok_scenes else _library.canonical_scenes_for(code)
    scenes_source = "grok" if grok_scenes else ("canonical" if scenes else None)
    overall = _library.canonical_summary_for(code) or base.synopsis_ko
    fav = int(getattr(row, "favorite_score", 0) or 0)
    flags_map = _library.load_file_flags_for([row.product_code])
    media = _library.media_flags_for(row, flags_map.get(row.product_code))
    watch = _library.load_watch_flags_for([code]).get(code.upper()) or {}
    from javstory.services.grok_story_service import grok_story_status

    grok_st = grok_story_status(code)
    return base.model_copy(
        update={
            "scene_count": len(scenes),
            "favorite_score": fav,
            "has_subtitle": media["has_subtitle"],
            "has_hardcoded_subtitle": media["has_hardcoded_subtitle"],
            "has_mosaic_removed": media["has_mosaic_removed"],
            "has_preview": media["has_preview"],
            "preview_media": media["preview_media"],
            "scenes": [SceneSummary(**s) for s in scenes],
            "scenes_source": scenes_source,
            "overall_summary": overall,
            "snapshot_count": _library.snapshot_count_for(code),
            "has_grok_story": bool(grok_st.get("has_cache")),
            "grok_story_running": bool(grok_st.get("running")),
            "user_liked": bool(watch.get("user_liked")),
            "watch_later": bool(watch.get("watch_later")),
            **_folder_watch_flags(code),
        }
    )


@router.get("/{code}", response_model=LibraryItemDetail)
def get_detail(code: str):
    row = _library.get_by_code(code)
    if not row:
        raise HTTPException(404, "작품을 찾을 수 없습니다")
    return _to_detail(row, code)


@router.patch("/{code}", response_model=LibraryItemDetail)
def update_library_item(code: str, body: LibraryItemUpdate):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "수정할 필드가 없습니다")
    row = _library.update_item(code, data)
    if not row:
        raise HTTPException(404, "작품을 찾을 수 없습니다")
    return _to_detail(row, code.upper())
