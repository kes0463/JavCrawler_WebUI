"""Post-STT filters for dialogue-focused subtitles (drop moans, hallucinations, noise)."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Optional

OptionalLogger = Optional[Callable[[str], None]]

# Mostly non-linguistic / effect-only lines
_NON_DIALOGUE_PATTERNS = (
    re.compile(r"^[ぁ-んァ-ンa-zA-Z0-9\s…\.!?、。ー〜~♡♥]+$"),  # too sparse — kept loose
    re.compile(r"^(あ+|う+|ん+|はぁ+|哈+|嗯+|呃+)[\.…!！?？]*$", re.I),
    re.compile(r"^(m+|ah+|oh+|ha+|hn+)[\.…!！?？]*$", re.I),
    re.compile(r"^[\W_]+$"),
)

_MIN_DIALOGUE_CHARS = 2
_MAX_NO_SPEECH_PROB = 0.65
_MAX_COMPRESSION_RATIO = 3.5
_MIN_AVG_LOGPROB = -1.2


def _is_non_dialogue_text(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < _MIN_DIALOGUE_CHARS:
        return True
    for pat in _NON_DIALOGUE_PATTERNS:
        if pat.match(t):
            return True
    # Very short kana-only moan-like
    if len(t) <= 4 and re.fullmatch(r"[ぁ-んァ-ンー…\.!！?？]+", t):
        if re.search(r"(あ{2,}|う{2,}|ん{2,}|はぁ)", t):
            return True
    return False


def _segment_metrics(seg: Any) -> tuple[float, float, float]:
    no_speech = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
    comp = float(getattr(seg, "compression_ratio", 0.0) or 0.0)
    logprob = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
    return no_speech, comp, logprob


def should_drop_segment(text: str, seg: Any | None = None) -> bool:
    if _is_non_dialogue_text(text):
        return True
    if seg is None:
        return False
    no_speech, comp, logprob = _segment_metrics(seg)
    if no_speech >= _MAX_NO_SPEECH_PROB:
        return True
    if comp >= _MAX_COMPRESSION_RATIO and len((text or "").strip()) < 8:
        return True
    if logprob < _MIN_AVG_LOGPROB and len((text or "").strip()) < 6:
        return True
    return False


def filter_whisper_result(result: Any) -> Any:
    """Remove non-dialogue segments from a stable_whisper WhisperResult in-place."""
    segments = getattr(result, "segments", None)
    if segments is None:
        return result
    kept = []
    for seg in segments:
        text = getattr(seg, "text", "") or ""
        if should_drop_segment(text, seg):
            continue
        kept.append(seg)
    result.segments = kept
    return result


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _sticky_hallucination_params() -> tuple[float, int, float, float, bool]:
    """(max_dur, short_text_chars, max_display_sec, early_window_sec, drop_early)."""
    try:
        max_dur = float(os.environ.get("JAVSTORY_STT_STICKY_MAX_DUR_SEC", "6") or "6")
    except ValueError:
        max_dur = 6.0
    try:
        short_len = int(os.environ.get("JAVSTORY_STT_STICKY_SHORT_CHARS", "12") or "12")
    except ValueError:
        short_len = 12
    try:
        display = float(os.environ.get("JAVSTORY_STT_STICKY_DISPLAY_SEC", "3.5") or "3.5")
    except ValueError:
        display = 3.5
    try:
        early = float(os.environ.get("JAVSTORY_STT_STICKY_EARLY_SEC", "60") or "60")
    except ValueError:
        early = 60.0
    drop_early = _env_bool("JAVSTORY_STT_DROP_EARLY_STICKY", False)
    return max_dur, short_len, display, early, drop_early


def fix_sticky_hallucination_segments(
    result: Any,
    *,
    logger: OptionalLogger = None,
) -> Any:
    """짧은 헛자막에 긴 end가 붙는 경우(예: 1s~17s '起立')를 제거·축소.

  Whisper가 초반 무음/BGM에서 단어를 환각하고, 실제 발화 시점까지 세그먼트 end를
  늘리면 플레이어에서 자막이 오래 유지된다. 짧은 텍스트 + 비정상 길이면 잘라낸다.
    """
    if not _env_bool("JAVSTORY_STT_FIX_STICKY_HALLUCINATION", True):
        return result
    segments = getattr(result, "segments", None)
    if not segments:
        return result

    max_dur, short_len, display_sec, early_window, drop_early = _sticky_hallucination_params()
    kept = []
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        start = float(getattr(seg, "start", 0.0) or 0.0)
        end = float(getattr(seg, "end", start) or start)
        dur = max(0.0, end - start)
        if dur <= max_dur or len(text) > short_len:
            kept.append(seg)
            continue

        no_speech, comp, logprob = _segment_metrics(seg)
        suspicious = (
            no_speech >= 0.5
            or comp >= 3.2
            or logprob < -1.0
            or (start < early_window and no_speech >= 0.35)
        )
        if not suspicious:
            kept.append(seg)
            continue

        if drop_early and start < early_window and (
            no_speech >= 0.8 or logprob < -1.5 or comp >= 4.0
        ):
            if logger:
                logger(
                    f"[STT] 초반 긴 단문 자막 제거: {text!r} "
                    f"({start:.1f}–{end:.1f}s, no_speech={no_speech:.2f})"
                )
            continue

        new_end = start + min(display_sec, dur)
        if hasattr(seg, "end"):
            seg.end = new_end
        if logger:
            logger(
                f"[STT] 긴 단문 자막 구간 축소: {text!r} "
                f"{start:.1f}–{end:.1f}s → {start:.1f}–{new_end:.1f}s"
            )
        kept.append(seg)

    result.segments = kept
    return result
