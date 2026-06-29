"""라이브러리 작품 메타데이터 수동 편집 — jav_metadata 행 반영 및 크롤 보호."""

from __future__ import annotations

from typing import Any

HARVEST_FAILED_TITLE_MARKER = "(수집 실패/정보 없음)"

_EDITABLE_FIELDS = frozenset({
    "title_ko",
    "title_ja",
    "title_en",
    "synopsis_ko",
    "synopsis_ja",
    "synopsis_en",
    "actors_ko",
    "actors_ja",
    "actors_romaji",
    "actors_en",
    "genres_ko",
    "genres_ja",
    "maker_ko",
    "maker_ja",
    "maker_en",
    "release_date",
})


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _opt_str(v: Any) -> str | None:
    s = _s(v)
    return s or None


def apply_library_metadata_fields(row: Any, data: dict[str, Any]) -> None:
    """세션 내 ORM 행에 편집 필드를 반영(commit은 호출자)."""
    payload = {k: v for k, v in data.items() if k in _EDITABLE_FIELDS}

    if "title_ko" in payload:
        row.title_ko = _opt_str(payload["title_ko"])
        row.title = row.title_ko
    if "title_ja" in payload:
        row.title_ja = _opt_str(payload["title_ja"])
        row.original_title = row.title_ja
    if "title_en" in payload:
        row.title_en = _opt_str(payload["title_en"])

    if "synopsis_ko" in payload:
        row.synopsis_ko = _opt_str(payload["synopsis_ko"])
        row.synopsis = row.synopsis_ko
    if "synopsis_ja" in payload:
        row.synopsis_ja = _opt_str(payload["synopsis_ja"])
    if "synopsis_en" in payload:
        row.synopsis_en = _opt_str(payload["synopsis_en"])

    if "actors_ko" in payload:
        row.actors_ko = _opt_str(payload["actors_ko"])
        row.actors = row.actors_ko
    if "actors_ja" in payload:
        row.actors_ja = _opt_str(payload["actors_ja"])
    if "actors_romaji" in payload:
        row.actors_romaji = _opt_str(payload["actors_romaji"])
    if "actors_en" in payload:
        en = _opt_str(payload["actors_en"])
        row.actors_en = en
        row.actors_zh_cn = en
        row.actors_zh_tw = en

    if "genres_ko" in payload:
        row.genres_ko = _opt_str(payload["genres_ko"])
        row.genres = row.genres_ko
    if "genres_ja" in payload:
        row.genres_ja = _opt_str(payload["genres_ja"])

    if "maker_ko" in payload:
        row.maker_ko = _opt_str(payload["maker_ko"])
        row.maker = row.maker_ko
    if "maker_ja" in payload:
        row.maker_ja = _opt_str(payload["maker_ja"])
    if "maker_en" in payload:
        row.maker_en = _opt_str(payload["maker_en"])

    if "release_date" in payload:
        row.release_date = _opt_str(payload["release_date"])


def mark_metadata_as_manual(row: Any) -> None:
    """수동 편집 표시 — 재크롤 실패 시 미수집 상태로 되돌리지 않음."""
    row.metadata_manual = True
    status = _s(getattr(row, "analysis_status", None))
    if status == "FAILED_CRAWL":
        row.analysis_status = "MANUAL"
    title_ko = _s(getattr(row, "title_ko", None))
    if HARVEST_FAILED_TITLE_MARKER in title_ko:
        row.title_ko = None
        row.title = None


def is_metadata_manual_protected(row: Any | None) -> bool:
    return bool(row is not None and getattr(row, "metadata_manual", False))


def harvest_merge_empty_only(row: Any | None, *, force_rebuild: bool) -> bool:
    """하베스트 upsert 시 merge_empty_only 여부.

    수동 편집(`metadata_manual`) 행은 재크롤(force_rebuild) 중에도
    빈 크롤·번역 결과로 기존 필드를 지우지 않는다.
    """
    if is_metadata_manual_protected(row):
        return True
    return not bool(force_rebuild)
