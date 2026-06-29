"""library_service 메타데이터 통계 필터 — SQL NULL 안전."""

from __future__ import annotations

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from javstory.harvest.database import Base, JAVMetadata
from javstory.services.library_service import (
    HARVEST_FAILED_TITLE_MARKER,
    _has_real_metadata_filter,
    _without_metadata_filter,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_has_real_metadata_counts_null_analysis_status_as_collected() -> None:
    """analysis_status=NULL + title_ko 있음 → 수집 완료 (NOT NULL SQL 함정 방지)."""
    session = _session()
    session.add(
        JAVMetadata(
            product_code="ABC-123",
            title_ko="테스트 제목",
            analysis_status=None,
        )
    )
    session.commit()

    has = session.query(func.count()).filter(_has_real_metadata_filter()).scalar()
    without = session.query(func.count()).filter(_without_metadata_filter()).scalar()
    assert has == 1
    assert without == 0


def test_without_metadata_counts_failed_crawl_placeholder() -> None:
    session = _session()
    session.add(
        JAVMetadata(
            product_code="FAIL-001",
            title_ko=f"[FAIL-001] {HARVEST_FAILED_TITLE_MARKER}",
            analysis_status="FAILED_CRAWL",
        )
    )
    session.commit()

    has = session.query(func.count()).filter(_has_real_metadata_filter()).scalar()
    without = session.query(func.count()).filter(_without_metadata_filter()).scalar()
    assert has == 0
    assert without == 1
