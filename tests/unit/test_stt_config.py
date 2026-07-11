"""Unit tests for STT engine config."""

from __future__ import annotations

import os

import pytest

from javstory.transcription.stt_config import (
    STT_ENGINE_ANIME_WHISPER,
    STT_ENGINE_STABLE_TS,
    STT_ENGINE_STABLE_TS_FW,
    dialogue_only_from_env,
    normalize_stt_engine,
    stt_engine_from_env,
    vad_threshold_from_env,
)


def test_normalize_stt_engine_aliases() -> None:
    assert normalize_stt_engine("stable-ts") == STT_ENGINE_STABLE_TS
    assert normalize_stt_engine("faster-whisper") == STT_ENGINE_STABLE_TS_FW
    assert normalize_stt_engine("anime-whisper") == STT_ENGINE_ANIME_WHISPER
    assert normalize_stt_engine("unknown") == STT_ENGINE_STABLE_TS


def test_stt_engine_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_STT_ENGINE", "anime_whisper")
    assert stt_engine_from_env() == STT_ENGINE_ANIME_WHISPER


def test_vad_threshold_dialogue_only_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_VAD_THRESHOLD", "0.30")
    monkeypatch.setenv("JAVSTORY_STT_DIALOGUE_ONLY", "1")
    assert vad_threshold_from_env() >= 0.45


def test_dialogue_only_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_STT_DIALOGUE_ONLY", "true")
    assert dialogue_only_from_env() is True
    monkeypatch.delenv("JAVSTORY_STT_DIALOGUE_ONLY", raising=False)
    assert dialogue_only_from_env() is False
