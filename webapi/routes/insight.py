from __future__ import annotations

from fastapi import APIRouter, Query

from javstory.services.insight_service import InsightService
from webapi.schemas import (
    InsightCollectionResponse,
    InsightOverviewResponse,
    InsightRecommendResponse,
    InsightTrendsResponse,
)

router = APIRouter()
_insight = InsightService()


@router.get("/overview", response_model=InsightOverviewResponse)
def insight_overview(force: bool = Query(False, description="캐시 무시 재조회")):
    data = _insight.fetch_overview(force_refresh=force)
    return InsightOverviewResponse(**data)


@router.get("/trends", response_model=InsightTrendsResponse)
def insight_trends():
    data = _insight.fetch_trends()
    return InsightTrendsResponse(**data)


@router.get("/recommend", response_model=InsightRecommendResponse)
def insight_recommend(force: bool = Query(False, description="추천 캐시 무시 재조회")):
    data = _insight.fetch_recommend(force_refresh=force)
    return InsightRecommendResponse(**data)


@router.get("/collection", response_model=InsightCollectionResponse)
def insight_collection(force: bool = Query(False)):
    data = _insight.fetch_collection(force_refresh=force)
    return InsightCollectionResponse(**data)


@router.post("/refresh", response_model=InsightOverviewResponse)
def insight_refresh():
    """주간 리포트·분포 캐시 등을 갱신하고 overview를 반환."""
    _insight.invalidate_recommend_cache()
    data = _insight.fetch_overview(force_refresh=True)
    return InsightOverviewResponse(**data)
