from __future__ import annotations

from fastapi import APIRouter, HTTPException

from javstory.folder_watch.candidates import search_folder_candidates
from javstory.folder_watch.inbox import clear_inbox, load_inbox, remove_inbox_item, upsert_inbox_item
from javstory.folder_watch.paused import is_monitoring_paused, pause_monitoring, resume_monitoring
from javstory.folder_watch.service import get_folder_watch_service
from webapi.schemas import (
    FolderBindingCandidatesRequest,
    FolderBindingCandidatesResponse,
    FolderBindingInboxItemSchema,
    FolderBindingInboxResponse,
)

router = APIRouter()
_svc = get_folder_watch_service()


def _inbox_response() -> FolderBindingInboxResponse:
    items = [
        FolderBindingInboxItemSchema(
            product_code=i.product_code,
            old_path=i.old_path,
            candidates=list(i.candidates),
            monitoring_paused=is_monitoring_paused(i.product_code),
        )
        for i in load_inbox()
    ]
    return FolderBindingInboxResponse(revision=_svc.revision, items=items)


def _bump_after_inbox_change() -> None:
    _svc.notify_change()


@router.get("/inbox", response_model=FolderBindingInboxResponse)
def get_inbox():
    return _inbox_response()


@router.delete("/inbox/{code}", response_model=FolderBindingInboxResponse)
def remove_from_inbox(code: str):
    pc = (code or "").strip().upper()
    if not pc:
        raise HTTPException(400, "품번이 필요합니다")
    remove_inbox_item(pc)
    _bump_after_inbox_change()
    return _inbox_response()


@router.post("/inbox/clear", response_model=FolderBindingInboxResponse)
def clear_inbox_items():
    clear_inbox()
    _bump_after_inbox_change()
    return _inbox_response()


@router.post("/candidates", response_model=FolderBindingCandidatesResponse)
def search_candidates(body: FolderBindingCandidatesRequest):
    pc = (body.product_code or "").strip().upper()
    if not pc:
        raise HTTPException(400, "품번이 필요합니다")
    cands = search_folder_candidates(pc, old_path=body.old_path or None)
    return FolderBindingCandidatesResponse(candidates=cands)


@router.post("/candidates/refresh", response_model=FolderBindingInboxResponse)
def refresh_inbox_candidates(body: FolderBindingCandidatesRequest):
    """인박스 항목의 후보 경로를 다시 검색해 갱신."""
    pc = (body.product_code or "").strip().upper()
    if not pc:
        raise HTTPException(400, "품번이 필요합니다")
    old_path = body.old_path or ""
    cands = search_folder_candidates(pc, old_path=old_path or None)
    upsert_inbox_item(pc, old_path, cands)
    _bump_after_inbox_change()
    return _inbox_response()


@router.post("/pause/{code}", response_model=FolderBindingInboxResponse)
def pause_monitoring_for_product(code: str):
    pc = (code or "").strip().upper()
    if not pc:
        raise HTTPException(400, "품번이 필요합니다")
    pause_monitoring(pc)
    _svc.clear_broken_flag(pc)
    _bump_after_inbox_change()
    return _inbox_response()


@router.post("/resume/{code}", response_model=FolderBindingInboxResponse)
def resume_monitoring_for_product(code: str):
    pc = (code or "").strip().upper()
    if not pc:
        raise HTTPException(400, "품번이 필요합니다")
    resume_monitoring(pc)
    _svc.clear_broken_flag(pc)
    _bump_after_inbox_change()
    _svc.refresh_paths_from_db()
    return _inbox_response()


@router.post("/verify")
def trigger_verify():
    """즉시 폴더 연결 상태 재검사 (디버그·수동 갱신용)."""
    _svc.refresh_paths_from_db()
    _svc.verify_bindings()
    return {"ok": True, "revision": _svc.revision}
