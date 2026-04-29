"""detail_persist.merge_scene_edit_with_previous 스모크 테스트."""

from __future__ import annotations

from javstory.library.canonical.schema import SceneEntry
from javstory.library.detail_persist import merge_scene_edit_with_previous


def test_merge_preserves_stills_when_time_unchanged():
    prev = [
        SceneEntry(
            scene_id="a",
            time_range="00:01:00 ~ 00:02:00",
            still_paths=["/x/1.jpg"],
            locked_fields={"scene_label"},
        )
    ]
    edited = [
        SceneEntry(
            scene_id="a",
            time_range="00:01:00 ~ 00:02:00",
            scene_label="new",
            still_paths=[],
        )
    ]
    out = merge_scene_edit_with_previous(prev, edited)
    assert len(out) == 1
    assert out[0].still_paths == ["/x/1.jpg"]
    assert out[0].scene_label == "new"


def test_merge_clears_stills_when_time_changes():
    prev = [
        SceneEntry(
            scene_id="a",
            time_range="00:01:00 ~ 00:02:00",
            still_paths=["/x/1.jpg"],
        )
    ]
    edited = [
        SceneEntry(
            scene_id="a",
            time_range="00:01:00 ~ 00:03:00",
            still_paths=[],
        )
    ]
    out = merge_scene_edit_with_previous(prev, edited)
    assert out[0].still_paths == []
    assert out[0].needs_still_refresh is True
