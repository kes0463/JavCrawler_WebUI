"""canonical JSON 라운드트립·미디어 바인딩."""

from __future__ import annotations

from javstory.library.canonical.schema import (
    CANONICAL_SCHEMA_VERSION,
    LibraryCanonical,
    MediaBinding,
    SceneEntry,
    VideoPartRef,
    library_canonical_from_grok_dict,
)


def test_library_canonical_round_trip() -> None:
    s = LibraryCanonical(
        product_code="TST-001",
        title_ja="題",
        title_ko="제목",
        scenes=[
            SceneEntry(scene_id="s1", time_range="00:00:01 ~ 00:00:10", scene_summary="요약"),
        ],
    )
    d = s.to_json_dict()
    back = LibraryCanonical.from_json_dict(d)
    assert back.product_code == "TST-001"
    assert back.scenes[0].scene_id == "s1"
    assert back.scenes[0].scene_summary == "요약"
    assert back.canonical_schema_version == CANONICAL_SCHEMA_VERSION


def test_media_binding_parts_round_trip() -> None:
    inner = LibraryCanonical(
        product_code="X-002",
        media=MediaBinding(
            primary_video_relpath="media/X.mp4",
            parts=[
                VideoPartRef(order=0, video_relpath="a.mp4", duration_sec=100.0),
                VideoPartRef(order=1, video_relpath="b.mp4", duration_sec=200.5),
            ],
            merged_timeline_srt_relpath="merged.ja.srt",
        ),
    )
    d = inner.to_json_dict()
    out = LibraryCanonical.from_json_dict(d)
    assert out.media is not None
    assert out.media.merged_timeline_srt_relpath == "merged.ja.srt"
    assert len(out.media.parts) == 2
    assert out.media.parts[1].duration_sec == 200.5


def test_library_canonical_from_grok_minimal() -> None:
    grok = {
        "product_code": "ABC-100",
        "schema_version": 1,
        "scenes": [
            {
                "scene_id": "1",
                "time_range": "00:01:00 ~ 00:02:00",
                "scene_label": "L",
                "scene_summary": "S",
                "tone": "T",
                "key_tags": ["a"],
            }
        ],
    }
    c = library_canonical_from_grok_dict(grok)
    assert c.product_code == "ABC-100"
    assert len(c.scenes) == 1
    assert c.scenes[0].start_sec is not None
    assert c.scenes[0].end_sec is not None
