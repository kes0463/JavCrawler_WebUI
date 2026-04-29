from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_, func

from javstory.harvest.database import get_db_session_ctx, JAVMetadata
from api.schemas import (
    LibraryItem, LibraryItemDetail,
    LibraryListResponse, LibraryStats,
)

router = APIRouter()

_SORT_COLS = {
    "updated_at": JAVMetadata.updated_at,
    "created_at": JAVMetadata.created_at,
    "release_date": JAVMetadata.release_date,
    "product_code": JAVMetadata.product_code,
    "title_ko": JAVMetadata.title_ko,
}


@router.get("", response_model=LibraryListResponse)
def list_library(
    q: str = Query("", description="검색어 (품번/제목/배우)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    sort: str = Query("updated_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    has_folder: Optional[bool] = None,
    has_metadata: Optional[bool] = None,
):
    with get_db_session_ctx() as db:
        query = db.query(JAVMetadata)

        if q:
            term = f"%{q}%"
            query = query.filter(or_(
                JAVMetadata.product_code.ilike(term),
                JAVMetadata.title_ko.ilike(term),
                JAVMetadata.title_ja.ilike(term),
                JAVMetadata.actors_ko.ilike(term),
                JAVMetadata.actors_ja.ilike(term),
            ))

        if has_folder is True:
            query = query.filter(JAVMetadata.folder_path.isnot(None))
        elif has_folder is False:
            query = query.filter(JAVMetadata.folder_path.is_(None))

        if has_metadata is True:
            query = query.filter(
                JAVMetadata.title_ko.isnot(None),
                JAVMetadata.title_ko != "",
            )
        elif has_metadata is False:
            query = query.filter(
                or_(JAVMetadata.title_ko.is_(None), JAVMetadata.title_ko == "")
            )

        total = query.count()

        sort_col = _SORT_COLS.get(sort, JAVMetadata.updated_at)
        query = query.order_by(
            sort_col.desc() if order == "desc" else sort_col.asc()
        )

        rows = query.offset((page - 1) * per_page).limit(per_page).all()

        return LibraryListResponse(
            total=total,
            page=page,
            per_page=per_page,
            items=[LibraryItem.model_validate(r) for r in rows],
        )


@router.get("/stats", response_model=LibraryStats)
def library_stats():
    with get_db_session_ctx() as db:
        total = db.query(func.count(JAVMetadata.id)).scalar() or 0
        with_metadata = db.query(func.count(JAVMetadata.id)).filter(
            JAVMetadata.title_ko.isnot(None),
            JAVMetadata.title_ko != "",
        ).scalar() or 0
        with_folder = db.query(func.count(JAVMetadata.id)).filter(
            JAVMetadata.folder_path.isnot(None),
        ).scalar() or 0

        return LibraryStats(
            total=total,
            with_metadata=with_metadata,
            with_folder=with_folder,
            without_metadata=total - with_metadata,
        )


@router.get("/cover/{code}")
def get_cover(code: str):
    """로컬에 저장된 표지 이미지를 반환합니다."""
    with get_db_session_ctx() as db:
        row = db.query(JAVMetadata).filter_by(
            product_code=code.upper()
        ).first()
        if not row:
            raise HTTPException(404, "작품을 찾을 수 없습니다")

        for path_field in (row.cover_image_local_path, row.thumb_image_local_path):
            if path_field:
                p = Path(path_field)
                if p.is_file():
                    return FileResponse(str(p), media_type="image/jpeg")

        raise HTTPException(404, "표지 이미지가 없습니다")


@router.get("/{code}", response_model=LibraryItemDetail)
def get_detail(code: str):
    with get_db_session_ctx() as db:
        row = db.query(JAVMetadata).filter_by(
            product_code=code.upper()
        ).first()
        if not row:
            raise HTTPException(404, "작품을 찾을 수 없습니다")
        return LibraryItemDetail.model_validate(row)
