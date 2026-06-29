from __future__ import annotations

from fastapi import APIRouter, Query

from javstory.services.dashboard_service import DashboardService
from webapi.schemas import (
    CancelPendingRequest,
    DashboardSummary,
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
        mosaic_queue_count=data["mosaic_queue_count"],
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


@router.post("/pending/cancel")
def cancel_pending(body: CancelPendingRequest):
    ok = _dashboard.cancel_pending(body.product_code)
    return {"ok": ok}


@router.post("/pending/clear")
def clear_pending():
    count = _dashboard.clear_pending()
    return {"ok": True, "cleared": count}
