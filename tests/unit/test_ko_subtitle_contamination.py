"""한글 자막 혼입 감지."""

from __future__ import annotations

import pytest

from javstory.translation.ko_translation_chunk import (
    has_ko_subtitle_contamination,
    is_acceptable_ko_subtitle_line,
    scrub_ja_residue_from_ko_line,
)


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("춥다ね", "춥다"),
        ("춥다ね, 잔뜩 샀네", "춥다, 잔뜩 샀네"),
        ("だって 싸쌌잖아. 세일이었으니까", "싸쌌잖아. 세일이었으니까"),
        ("너무 많이 산 거 아니야?", "너무 많이 산 거 아니야?"),
        ("寒いね", "寒いね"),  # 한글 없음 → 유지(품질 실패 유도)
    ],
)
def test_scrub_ja_residue(raw: str, expected: str) -> None:
    got = scrub_ja_residue_from_ko_line(raw)
    assert got == expected
    if got != raw and any("\uac00" <= ch <= "\ud7a3" for ch in got):
        assert is_acceptable_ko_subtitle_line(got)
