"""Grok 초안 병합 — 잠긴 필드 유지."""

from __future__ import annotations

import pytest

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry
from javstory.library.grok_merge.merge import merge_grok_draft


def test_merge_respects_scene_locked_summary() -> None:
    base = LibraryCanonical(
        product_code="ABC-123",
        scenes=[
            SceneEntry(
                scene_id="1",
                time_range="00:00:00 ~ 00:01:00",
                scene_summary="사용자 확정 요약",
                locked_fields={"scene_summary"},
            )
        ],
    )
    grok = {
        "product_code": "ABC-123",
        "scenes": [
            {
                "scene_id": "1",
                "time_range": "00:00:00 ~ 00:01:00",
                "scene_summary": "Grok가 준 다른 요약",
            }
        ],
    }
    out = merge_grok_draft(base, grok)
    assert out.scenes[0].scene_summary == "사용자 확정 요약"


def test_merge_product_code_mismatch_raises() -> None:
    base = LibraryCanonical(product_code="A-1")
    grok = {"product_code": "B-2", "scenes": []}
    with pytest.raises(ValueError, match="품번"):
        merge_grok_draft(base, grok)
