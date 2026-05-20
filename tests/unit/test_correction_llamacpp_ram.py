"""llama.cpp 교정 RAM 관련 청크·동시성."""

from __future__ import annotations

import pytest

from javstory.config.app_config import correction_llm_tier
from javstory.translation.correction_chunk import (
    _correction_concurrency,
    _default_pass2_concurrency,
    _effective_chunk_durations,
)


def test_llamacpp_ignores_global_correction_chunk_env(monkeypatch):
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_MODEL", "llamacpp:qwen3.5-35b-a3b-uncensored")
    monkeypatch.setenv("JAVSTORY_CORRECTION_CHUNK_TARGET_SEC", "80")
    monkeypatch.setenv("JAVSTORY_CORRECTION_CHUNK_OVERLAP_SEC", "20")
    tier = correction_llm_tier(2)
    tgt, ov = _effective_chunk_durations(tier)
    assert tgt == pytest.approx(16.0)
    assert ov == pytest.approx(4.5)


def test_llamacpp_pass2_concurrency_clamped(monkeypatch):
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_CONCURRENCY", "4")
    tier = {"provider": "llamacpp"}
    assert _default_pass2_concurrency(tier) == 1
    assert _correction_concurrency("pass2", 1) == 4  # env still read; caller clamps


def test_correction_llamacpp_max_tokens_default(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:qwen3.5-35b-a3b-uncensored",
    )
    monkeypatch.delenv("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", raising=False)
    tier = correction_llm_tier(2)
    assert tier["max_tokens"] == 3072
    assert tier["max_ctx"] == 4096
