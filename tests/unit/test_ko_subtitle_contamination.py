"""한글 자막 혼입 감지."""

from __future__ import annotations

import pytest

from javstory.translation.ko_translation_chunk import has_ko_subtitle_contamination


@pytest.mark.parametrize(
    "text",
    [
        "제대로 바anko 보여줘",
        "濡라줘",
        "hello",
        "아아ん",
        "좋아요",
    ],
)
def test_ko_contamination_detected(text: str) -> None:
    if text == "좋아요":
        assert not has_ko_subtitle_contamination(text)
    else:
        assert has_ko_subtitle_contamination(text)
