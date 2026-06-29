"""LibraryService list/scene count performance tests."""

from __future__ import annotations

import javstory.services.library_service as mod
from javstory.services.library_service import LibraryService


def test_scene_counts_for_skips_non_story(monkeypatch) -> None:
    svc = LibraryService()
    monkeypatch.setattr(
        svc,
        "_grok_story_cache",
        lambda _pc: {"scenes": [{}, {}, {}]},
    )
    flags = {
        "AAA-001": {"has_story": 0},
        "BBB-002": {"has_story": 1},
    }
    counts = svc.scene_counts_for(["AAA-001", "BBB-002"], flags)
    assert counts["AAA-001"] == 0
    assert counts["BBB-002"] == 3


def test_scene_counts_for_empty_codes() -> None:
    svc = LibraryService()
    assert svc.scene_counts_for([], {}) == {}


def test_stats_cache_hit() -> None:
    mod._STATS_CACHE = None
    payload = {
        "total": 10,
        "with_metadata": 8,
        "with_folder": 5,
        "without_metadata": 2,
    }
    mod._STATS_CACHE = (mod.time.time(), payload)
    cached = mod._STATS_CACHE[1]
    assert cached["total"] == 10
    assert cached["with_metadata"] == 8
