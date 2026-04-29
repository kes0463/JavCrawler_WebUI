"""gui.library_data 정렬·필터."""

from __future__ import annotations

from gui.library_data import (
    LibraryWorkSummary,
    filter_summaries,
    sort_summaries,
)


def _s(
    pc: str,
    *,
    updated: str = "2026-01-01T00:00:00",
    scenes: int = 0,
    canonical: bool = False,
) -> LibraryWorkSummary:
    return LibraryWorkSummary(
        product_code=pc,
        title_ko="",
        title_ja="",
        actors_ko="",
        maker_ko="",
        release_date="2025-01-01",
        synopsis_ko="",
        genres_ko="",
        cover_local_path=None,
        cover_image_url=None,
        has_canonical=canonical,
        scene_count=scenes,
        still_total=0,
        overall_summary_preview="",
        has_harvest=True,
        has_transcription=False,
        has_translation=False,
        is_hardcoded=False,
        is_mopa=False,
        has_ja_srt=False,
        has_ko_srt=False,
        lamp_hardcoded=False,
        lamp_mopa=False,
        pipeline_stage="harvest",
        cover_effective_path=None,
        cover_needs_download_flag=False,
        updated_at_iso=updated,
        folder_path=None,
    )


def test_sort_by_product_code() -> None:
    items = [_s("ZZZ-1"), _s("AAA-1")]
    out = sort_summaries(items, key="product_code", reverse=False)
    assert [x.product_code for x in out] == ["AAA-1", "ZZZ-1"]


def test_filter_canonical() -> None:
    items = [_s("A", canonical=True), _s("B", canonical=False)]
    out = filter_summaries(items, canonical_filter="has_canonical")
    assert len(out) == 1
    assert out[0].product_code == "A"


def test_filter_text() -> None:
    items = [_s("STAR-001"), _s("MIDE-002")]
    out = filter_summaries(items, text_query="mide")
    assert len(out) == 1
