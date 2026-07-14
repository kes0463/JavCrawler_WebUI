"""파이프라인 번역 노트(6섹션) 유틸."""

from __future__ import annotations

from javstory.transcription.stt_types import SimpleSegment
from javstory.translation.translation_note_generator import (
    _pipeline_note_user_payload,
    pipeline_note_looks_incomplete,
    sample_ja_dialogue_from_segments,
)
from javstory.translation.translation_notes import (
    PIPELINE_NOTE_SECTIONS,
    extract_glossary,
    parse_note_sections,
)


def test_sample_ja_dialogue_spreads_and_limits() -> None:
    segs = [SimpleSegment(float(i), float(i) + 1, f"대사{i}") for i in range(100)]
    sample = sample_ja_dialogue_from_segments(segs, max_chars=400, max_lines=20)
    assert "대사0" in sample
    assert len(sample) <= 400
    assert sample.count("\n") + 1 <= 20


def test_pipeline_sections_known_order() -> None:
    assert PIPELINE_NOTE_SECTIONS[0] == "기본 번역 규칙"
    assert PIPELINE_NOTE_SECTIONS[-1] == "번역 스타일 지침"
    assert len(PIPELINE_NOTE_SECTIONS) == 6


def test_extract_glossary_from_yong_eo_sajeon() -> None:
    note = (
        "[용어 사전]\n"
        "- ちはる => 치하루\n"
        "- だって => 왜냐면\n"
        "[말투에 대한 규칙]\n"
        "- 여주 반말\n"
    )
    gloss = dict(extract_glossary(note))
    assert gloss["ちはる"] == "치하루"
    assert gloss["だって"] == "왜냐면"


def test_parse_pipeline_note_sections() -> None:
    raw = "\n".join(
        f"[{h}]\n- item\n" for h in PIPELINE_NOTE_SECTIONS
    )
    sects = parse_note_sections(raw)
    for h in PIPELINE_NOTE_SECTIONS:
        assert h in sects.sections
        assert sects.sections[h]


def test_pipeline_note_looks_incomplete_truncated() -> None:
    truncated = (
        "[기본 번역 규칙]\n"
        "- 존댓말/반말은 화자와 청자의 관계에 따라 유연하게 적용한다.\n"
        "- 모든 번역은 한글 전용을 원"
    )
    assert pipeline_note_looks_incomplete(truncated) is True


def test_pipeline_note_looks_incomplete_vague_speech() -> None:
    note = "\n".join(
        f"[{h}]\n- 유연하게 적용한다.\n" for h in PIPELINE_NOTE_SECTIONS
    )
    assert pipeline_note_looks_incomplete(note) is True


def test_pipeline_note_looks_complete_six_sections() -> None:
    parts: list[str] = []
    for h in PIPELINE_NOTE_SECTIONS:
        if h == "말투에 대한 규칙":
            parts.append(f"[{h}]\n- (여성1) → (남성1): 반말\n- (남성1) → (여성1): 존댓말\n")
        else:
            parts.append(f"[{h}]\n- 항목입니다.\n")
    full = "\n".join(parts)
    assert pipeline_note_looks_incomplete(full) is False


def test_pipeline_note_payload_without_grok_uses_title_synopsis() -> None:
    payload = _pipeline_note_user_payload(
        product_code="ABW-001",
        grok_json=None,
        ja_sample="0: おはよう",
        title_ja="テスト作品",
        title_ko="테스트 작품",
        synopsis="짧은 줄거리입니다.",
    )
    assert "Grok 스토리 컨텍스트는 제공되지 않음" in payload
    assert "제목: 테스트 작품 / テスト作品" in payload
    assert "시놉시스:" in payload
    assert "짧은 줄거리입니다." in payload
    assert "[Grok 스토리 컨텍스트]" not in payload
    assert "おはよう" in payload


def test_pipeline_note_payload_with_grok_keeps_section() -> None:
    payload = _pipeline_note_user_payload(
        product_code="ABW-001",
        grok_json={"overall_summary": "긴 요약", "product_code": "ABW-001"},
        ja_sample="0: こんにちは",
        title_ja="タイトル",
        synopsis="시놉",
    )
    assert "[Grok 스토리 컨텍스트]" in payload
    assert "제목:" in payload
    assert "Grok 스토리 컨텍스트는 제공되지 않음" not in payload


def test_generate_pipeline_note_without_grok_no_unbound_has_grok() -> None:
    """has_grok를 ja_sample보다 먼저 정의해야 UnboundLocalError가 나지 않는다."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from javstory.translation.translation_note_generator import (
        generate_pipeline_translation_note_async,
    )

    note_body = "\n".join(
        (
            f"[{h}]\n- (여성1) → (남성1): 반말\n"
            if h == "말투에 대한 규칙"
            else f"[{h}]\n- 항목\n"
        )
        for h in PIPELINE_NOTE_SECTIONS
    )
    router = MagicMock()
    router.gemini_client = None
    router.call_model = AsyncMock(return_value=note_body)
    router.close = AsyncMock()

    out = asyncio.run(
        generate_pipeline_translation_note_async(
            product_code="ABW-001",
            grok_json=None,
            ja_segments=[SimpleSegment(0.0, 1.0, "おはよう")],
            title_ja="テスト",
            synopsis="줄거리",
            router=router,
        )
    )
    assert "[기본 번역 규칙]" in out
    router.call_model.assert_awaited()
