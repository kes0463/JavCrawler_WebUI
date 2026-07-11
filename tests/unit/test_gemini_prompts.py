"""Unit tests for Gemini/HTML translation prompt helpers."""

from __future__ import annotations

from javstory.translation.gemini_prompts import parse_html_translation_response
from javstory.translation.ko_translation_chunk import (
    has_ko_subtitle_contamination,
    is_acceptable_ko_subtitle_line,
    segments_translation_quality_ok,
)
from javstory.transcription.stt_types import SimpleSegment


def test_parse_html_uses_translation_block_not_source() -> None:
    segs = [
        SimpleSegment(0.0, 1.0, "気持ちいい?"),
        SimpleSegment(1.0, 2.0, "起立"),
    ]
    raw = (
        '<main id="원문">\n'
        '<p id="0">気持ちいい?</p>\n'
        '<p id="1">起立</p>\n'
        "</main>\n"
        '<main id="번역">\n'
        '<p id="0">기분 좋아?</p>\n'
        '<p id="1">일어나</p>\n'
        "</main>"
    )
    assert parse_html_translation_response(raw, segs) is True
    assert segs[0].text == "기분 좋아?"
    assert segs[1].text == "일어나"


def test_parse_html_requires_all_segments() -> None:
    segs = [
        SimpleSegment(0.0, 1.0, "A"),
        SimpleSegment(1.0, 2.0, "B"),
    ]
    raw = '<main id="번역"><p id="0">가</p></main>'
    assert parse_html_translation_response(raw, segs) is False


def test_quality_rejects_japanese_and_mixed_lines() -> None:
    assert has_ko_subtitle_contamination("気持ちいい") is True
    assert has_ko_subtitle_contamination("気持ち 좋은 거") is True
    assert has_ko_subtitle_contamination("ชอบชอบ") is True
    assert is_acceptable_ko_subtitle_line("기분 좋아?") is True
    assert is_acceptable_ko_subtitle_line("気持ちいい") is False
    segs = [SimpleSegment(0, 1, "좋아"), SimpleSegment(1, 2, "気持ちいい")]
    assert segments_translation_quality_ok(segs) is False
