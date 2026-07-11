from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from javstory.services.dashboard_service import DashboardService
from webapi.schemas import (
    CancelPendingRequest,
    DashboardSummary,
    EmbeddingQueueStatus,
    LibraryStats,
    PendingItem,
    PreviewQueueStatus,
    SystemMetrics,
    WatchStats,
)

router = APIRouter()
_dashboard = DashboardService()


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary():
    data = _dashboard.summary()
    return DashboardSummary(
        library=LibraryStats(**data["library"]),
        watch=WatchStats(**data["watch"]),
        pending_count=data["pending_count"],
        metadata_match_rate=data["metadata_match_rate"],
    )


@router.get("/pending", response_model=list[PendingItem])
def pending_items(limit: int = Query(200, ge=1, le=500)):
    return [PendingItem(**item) for item in _dashboard.pending_items(limit=limit)]


@router.get("/system", response_model=SystemMetrics)
def system_metrics():
    return SystemMetrics(**_dashboard.system_metrics())


@router.get("/preview-queue", response_model=PreviewQueueStatus)
def preview_queue_status(limit: int = Query(40, ge=1, le=100)):
    from javstory.library.highlight.preview_queue import preview_queue_manager

    return PreviewQueueStatus(**preview_queue_manager.snapshot(limit=limit))


@router.get("/embedding-queue", response_model=EmbeddingQueueStatus)
def embedding_queue_status(limit: int = Query(40, ge=1, le=100)):
    from javstory.library.embeddings.embedding_queue import embedding_queue_manager

    return EmbeddingQueueStatus(**embedding_queue_manager.snapshot(limit=limit))


@router.delete("/embedding-queue/finished")
def clear_embedding_finished():
    from javstory.library.embeddings.embedding_queue import embedding_queue_manager

    removed = embedding_queue_manager.clear_finished()
    return {"ok": True, "removed": removed}


@router.delete("/embedding-queue/{job_id}")
def remove_embedding_job(job_id: str):
    from javstory.library.embeddings.embedding_queue import embedding_queue_manager

    if not embedding_queue_manager.remove_job(job_id):
        raise HTTPException(404, "작업을 찾을 수 없습니다") from None
    return {"ok": True}


@router.post("/pending/cancel")
def cancel_pending(body: CancelPendingRequest):
    ok = _dashboard.cancel_pending(body.product_code)
    return {"ok": ok}


@router.post("/pending/clear")
def clear_pending():
    count = _dashboard.clear_pending()
    return {"ok": True, "cleared": count}


@router.delete("/preview-queue/finished")
def clear_preview_finished():
    from javstory.library.highlight.preview_queue import preview_queue_manager

    removed = preview_queue_manager.clear_finished()
    return {"ok": True, "removed": removed}


@router.post("/preview-queue/pause-all")
def pause_all_preview():
    from javstory.library.highlight.preview_queue import preview_queue_manager

    preview_queue_manager.set_user_paused(True)
    return {"ok": True, "paused": True}


@router.post("/preview-queue/resume-all")
def resume_all_preview():
    from javstory.library.highlight.preview_queue import preview_queue_manager

    resumed = preview_queue_manager.resume_all_paused()
    return {"ok": True, "resumed": resumed}


@router.delete("/preview-queue/{job_id}")
def remove_preview_job(job_id: str):
    from javstory.library.highlight.preview_queue import preview_queue_manager

    if not preview_queue_manager.remove_job(job_id):
        raise HTTPException(404, "작업을 찾을 수 없습니다") from None
    return {"ok": True}


@router.post("/preview-queue/{job_id}/pause")
def pause_preview_job(job_id: str):
    from javstory.library.highlight.preview_queue import preview_queue_manager

    if not preview_queue_manager.pause_job(job_id):
        raise HTTPException(400, "일시정지할 수 없는 작업입니다") from None
    return {"ok": True}


@router.post("/preview-queue/{job_id}/resume")
def resume_preview_job(job_id: str):
    from javstory.library.highlight.preview_queue import preview_queue_manager

    if not preview_queue_manager.resume_job(job_id):
        raise HTTPException(400, "재개할 수 없는 작업입니다") from None
    return {"ok": True}
