from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from javstory.harvest.database import JAVMetadata
from javstory.services.library_service import LibraryService
from webapi.schemas import (
    CoverUploadResponse,
    FolderBindRequest,
    FolderBindResponse,
    LibraryItem,
    LibraryItemDetail,
    LibraryItemUpdate,
    LibraryListResponse,
    LibraryStats,
    OpenFolderResponse,
    SceneSummary,
)

router = APIRouter()
_library = LibraryService()


def _to_item(
    row: JAVMetadata,
    cache: dict | None = None,
    scene_counts: dict[str, int] | None = None,
) -> LibraryItem:
    base = LibraryItem.model_validate(row)
    fav = int(getattr(row, "favorite_score", 0) or 0)
    pc = (row.product_code or "").strip().upper()
    count = (scene_counts or {}).get(pc, 0)
    media = _library.media_flags_for(row, cache)
    return base.model_copy(
        update={
            "scene_count": count,
            "favorite_score": fav,
            "has_subtitle": media["has_subtitle"],
            "has_hardcoded_subtitle": media["has_hardcoded_subtitle"],
            "has_mosaic_removed": media["has_mosaic_removed"],
            "has_preview": media["has_preview"],
            "preview_media": media["preview_media"],
        }
    )


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
    has_mosaic_removed: Optional[bool] = None,
    include_total: bool = Query(True, description="false면 total 생략(append용)"),
):
    result = _library.list_items(
        q=q,
        page=page,
        per_page=per_page,
        sort=sort,
        order=order,
        has_folder=has_folder,
        has_metadata=has_metadata,
        has_subtitle=has_subtitle,
        has_mosaic_removed=has_mosaic_removed,
        include_total=include_total,
    )
    rows = result["items"]
    codes = [r.product_code for r in rows]
    flags_map = _library.load_file_flags_for(codes)
    scene_counts = _library.scene_counts_for(codes, flags_map)
    return LibraryListResponse(
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        items=[_to_item(r, flags_map.get(r.product_code), scene_counts) for r in rows],
    )


@router.get("/stats", response_model=LibraryStats)
def library_stats():
    return LibraryStats(**_library.stats())


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
        headers={"Cache-Control": "no-cache"},
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
