"""JSON cue-array extraction / Gemma translation helpers."""

from __future__ import annotations

from javstory.transcription.stt_types import SimpleSegment
from javstory.translation.correction_chunk import _apply_json_chunk
from javstory.translation.json_extract import parse_json_array
from javstory.translation.ko_translation_chunk import (
    _chunk_json_for_translation,
    _default_chunk_durations,
    is_acceptable_ko_subtitle_line,
    render_glm_translation_chunk_user,
    system_prompt_translation_chunk,
    system_prompt_translation_local_gemma,
    system_prompt_translation_local_gemma_retry,
)


def test_parse_single_quoted_pythonish_array() -> None:
    raw = "Sure.\n[{'index': 0, 'text': '안녕'}, {'index': 1, 'text': '뭐야'}]\n"
    arr = parse_json_array(raw)
    assert arr is not None
    assert arr[0]["text"] == "안녕"


def test_parse_smart_quotes_and_fence() -> None:
    raw = (
        "```json\n"
        "[\n"
        "{“index”: 0, “text”: “테스트”},\n"
        "{“index”: 1, “text”: “완료”}\n"
        "]\n"
        "```"
    )
    arr = parse_json_array(raw)
    assert arr is not None
    assert len(arr) == 2


def test_parse_truncated_array_recovers_complete_objects() -> None:
    raw = '[{"index": 0, "text": "하나"}, {"index": 1, "text": "둘", "broken":'
    arr = parse_json_array(raw)
    assert arr is not None
    assert arr[0]["text"] == "하나"


def test_apply_require_complete_rejects_partial() -> None:
    segs = [SimpleSegment(0.0, 1.0, "ja1"), SimpleSegment(1.0, 2.0, "ja2")]
    logs: list[str] = []
    ok = _apply_json_chunk(
        segs,
        '[{"index":0,"text":"하나"}]',
        log=logs.append,
        require_start_end=False,
        require_complete=True,
    )
    assert ok is False
    assert segs[0].text == "ja1"
    assert segs[1].text == "ja2"
    assert any("부분 적용" in m for m in logs)


def test_apply_require_complete_accepts_full() -> None:
    segs = [SimpleSegment(0.0, 1.0, "ja1"), SimpleSegment(1.0, 2.0, "ja2")]
    ok = _apply_json_chunk(
        segs,
        '[{"index":0,"text":"하나"},{"index":1,"text":"둘"}]',
        log=lambda _m: None,
        require_start_end=False,
        require_complete=True,
    )
    assert ok
    assert segs[0].text == "하나"
    assert segs[1].text == "둘"


def test_translation_chunk_json_omits_timestamps() -> None:
    segs = [SimpleSegment(10.5, 12.0, "こんにちは")]
    raw = _chunk_json_for_translation(segs)
    assert "start" not in raw
    assert "end" not in raw
    assert '"index": 0' in raw


def test_gemma_llamacpp_uses_english_json_system() -> None:
    prompt = system_prompt_translation_chunk(
        {"provider": "llamacpp", "model": "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q5_K_M"}
    )
    assert "ONLY" in prompt or "only" in prompt.lower()
    assert "JSON" in prompt


def test_gemma_retry_system_differs_from_primary() -> None:
    primary = system_prompt_translation_local_gemma()
    retry = system_prompt_translation_local_gemma_retry()
    assert retry != primary
    assert "RETRY" in retry.upper() or "CRITICAL" in retry.upper()


def test_gemma_user_prompt_english_local() -> None:
    user = render_glm_translation_chunk_user(
        '{"product_code":"X"}',
        '[{"index":0,"text":"こんにちは"}]',
        0,
        "S01",
        "calm",
        "",
        english_local=True,
    )
    assert "[Source JSON]" in user
    assert "[Background]" in user
    assert "[作品背景]" not in user


def test_non_lexical_source_allows_punctuation_ko() -> None:
    assert is_acceptable_ko_subtitle_line("…", source_ja="…") is True
    assert is_acceptable_ko_subtitle_line("あ", source_ja="…") is False


def test_llamacpp_gemma_chunk_longer_than_qwen() -> None:
    gemma_t, _ = _default_chunk_durations(
        {"provider": "llamacpp", "model": "gemma-4-e4b-uncensored"}
    )
    qwen_t, _ = _default_chunk_durations(
        {"provider": "llamacpp", "model": "Qwen2.5-14B-Instruct"}
    )
    assert gemma_t > qwen_t
