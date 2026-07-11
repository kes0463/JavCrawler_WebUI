"""Unit tests for dialogue-only STT post-filter."""

from __future__ import annotations

from javstory.transcription.dialogue_filter import (
    fix_sticky_hallucination_segments,
    should_drop_segment,
)


class _Seg:
    def __init__(self, no_speech_prob=0.0, compression_ratio=1.0, avg_logprob=0.0):
        self.no_speech_prob = no_speech_prob
        self.compression_ratio = compression_ratio
        self.avg_logprob = avg_logprob


def test_drop_moan_like_text() -> None:
    assert should_drop_segment("あああ…", _Seg()) is True
    assert should_drop_segment("んん", _Seg()) is True


def test_keep_dialogue() -> None:
    assert should_drop_segment("今日は本当に暑いですね。", _Seg()) is False


def test_drop_high_no_speech_prob() -> None:
    assert should_drop_segment("こんにちは", _Seg(no_speech_prob=0.9)) is True


class _Result:
    def __init__(self, segments: list[_Seg]) -> None:
        self.segments = segments


def test_fix_sticky_hallucination_trims_early_long_short_cue_by_default() -> None:
    seg = _Seg(no_speech_prob=0.5)
    seg.text = "起立"
    seg.start = 1.0
    seg.end = 17.0
    res = _Result([seg])
    fix_sticky_hallucination_segments(res)
    assert len(res.segments) == 1
    assert res.segments[0].end == 4.5


def test_fix_sticky_hallucination_can_drop_very_suspicious_early_cue(monkeypatch) -> None:
    monkeypatch.setenv("JAVSTORY_STT_DROP_EARLY_STICKY", "1")
    seg = _Seg(no_speech_prob=0.9, avg_logprob=-1.8)
    seg.text = "起立"
    seg.start = 1.0
    seg.end = 17.0
    res = _Result([seg])
    fix_sticky_hallucination_segments(res)
    assert res.segments == []


def test_fix_sticky_hallucination_keeps_normal_dialogue(monkeypatch) -> None:
    seg = _Seg()
    seg.text = "今日は本当に暑いですね。"
    seg.start = 1.0
    seg.end = 4.0
    res = _Result([seg])
    fix_sticky_hallucination_segments(res)
    assert len(res.segments) == 1
    assert res.segments[0].end == 4.0
