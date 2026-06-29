from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from javstory.services.actress_service import ActressService
from webapi.schemas import (
    ActressAliasItem,
    ActressCreateRequest,
    ActressListItem,
    ActressListResponse,
    ActressMergeRequest,
    ActressProfile,
    ActressResolveResponse,
    ActressSearchItem,
    ActressUpdateRequest,
    ActressWorksBundle,
    AliasCreateRequest,
)

router = APIRouter()
_svc = ActressService()


@router.get("", response_model=ActressListResponse)
def list_actresses(
    q: str = Query("", description="이름·장르·별명 검색"),
    sort: str = Query("name", pattern="^(name|works|favorite|score|recent)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(48, ge=1, le=200),
):
    result = _svc.list_actresses(
        q=q,
        sort=sort,
        ascending=(order == "asc"),
        page=page,
        per_page=per_page,
    )
    return ActressListResponse(**result)


@router.get("/search", response_model=list[ActressSearchItem])
def search_actresses(q: str = Query("", min_length=0), limit: int = Query(50, ge=1, le=100)):
    return _svc.search_actresses(q, limit=limit)


@router.get("/resolve", response_model=ActressResolveResponse)
def resolve_actress(name: str = Query(..., min_length=1)):
    aid = _svc.resolve_id_by_name(name)
    return ActressResolveResponse(name=name, actress_id=aid)


@router.get("/media")
def get_media(path: str = Query(..., min_length=1)):
    file_path = _svc.resolve_media_file(path)
    if not file_path:
        raise HTTPException(404, "이미지를 찾을 수 없습니다")
    suffix = Path(file_path).suffix.lower()
    media = "image/jpeg"
    if suffix == ".png":
        media = "image/png"
    elif suffix == ".webp":
        media = "image/webp"
    return FileResponse(file_path, media_type=media)


@router.get("/{actress_id}", response_model=ActressProfile)
def get_actress(actress_id: int):
    profile = _svc.get_profile(actress_id)
    if not profile:
        raise HTTPException(404, "배우를 찾을 수 없습니다")
    return ActressProfile(**profile)


@router.get("/{actress_id}/works", response_model=ActressWorksBundle)
def get_actress_works(actress_id: int):
    bundle = _svc.get_works_bundle(actress_id)
    return ActressWorksBundle(**bundle)


@router.post("", response_model=ActressProfile)
def create_actress(body: ActressCreateRequest):
    new_id = _svc.create_actress(body.model_dump(exclude_none=True))
    profile = _svc.get_profile(new_id)
    if not profile:
        raise HTTPException(500, "배우 생성 후 프로필을 불러올 수 없습니다")
    return ActressProfile(**profile)


@router.patch("/{actress_id}", response_model=ActressProfile)
def update_actress(actress_id: int, body: ActressUpdateRequest):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "변경할 필드가 없습니다")
    if not _svc.update_actress(actress_id, data):
        raise HTTPException(404, "배우를 찾을 수 없습니다")
    profile = _svc.get_profile(actress_id)
    if not profile:
        raise HTTPException(404, "배우를 찾을 수 없습니다")
    return ActressProfile(**profile)


@router.post("/{actress_id}/merge")
def merge_actresses(actress_id: int, body: ActressMergeRequest):
    if actress_id == body.merge_id:
        raise HTTPException(400, "같은 배우는 합칠 수 없습니다")
    ok, linked = _svc.merge(actress_id, body.merge_id)
    if not ok:
        raise HTTPException(400, "배우 합치기에 실패했습니다")
    profile = _svc.get_profile(actress_id)
    return {
        "ok": True,
        "actress_id": actress_id,
        "linked_product_codes": linked,
        "profile": profile,
    }


@router.post("/{actress_id}/aliases", response_model=ActressAliasItem)
def add_alias(actress_id: int, body: AliasCreateRequest):
    if not _svc.add_alias(actress_id, body.alias_name, body.alias_type, is_primary=body.is_primary):
        raise HTTPException(400, "별명 추가에 실패했습니다")
    profile = _svc.get_profile(actress_id)
    if not profile:
        raise HTTPException(404, "배우를 찾을 수 없습니다")
    for a in profile.get("aliases") or []:
        if a.get("alias_name") == body.alias_name.strip():
            return ActressAliasItem(**a)
    raise HTTPException(500, "별명을 확인할 수 없습니다")


@router.delete("/{actress_id}/aliases/{alias_id}")
def remove_alias(actress_id: int, alias_id: int):
    if not _svc.remove_alias(actress_id, alias_id):
        raise HTTPException(404, "별명을 찾을 수 없습니다")
    return {"ok": True}


@router.post("/{actress_id}/images")
async def upload_image(
    actress_id: int,
    file: UploadFile = File(...),
    is_profile: bool = Query(False),
):
    import tempfile

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        saved = _svc.add_image(actress_id, tmp_path, is_profile=is_profile)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if not saved:
        raise HTTPException(400, "사진 저장에 실패했습니다")
    profile = _svc.get_profile(actress_id)
    return {"ok": True, "path": saved, "profile": profile}


@router.post("/{actress_id}/images/{image_id}/profile")
def set_profile_image(actress_id: int, image_id: int):
    if not _svc.set_profile_image(actress_id, image_id):
        raise HTTPException(400, "대표 사진 설정에 실패했습니다")
    profile = _svc.get_profile(actress_id)
    return {"ok": True, "profile": profile}
