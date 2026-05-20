"""correction_llm_tier Pass2 — Ollama / llama.cpp 접두사."""

from __future__ import annotations

import pytest

from javstory.config.app_config import correction_llm_tier
from javstory.llm.llamacpp_backend import resolve_llamacpp_preset


def test_correction_pass2_ollama(monkeypatch):
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_MODEL", "ollama:qwen3.5:9b")
    tier = correction_llm_tier(2)
    assert tier["provider"] == "ollama"
    assert tier["model"] == "qwen3.5:9b"
    assert tier.get("ollama_think") is False


def test_correction_pass2_llamacpp_uncensored(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    tier = correction_llm_tier(2)
    assert tier["provider"] == "llamacpp"
    assert tier["llamacpp_preset"] == "gemma-4-e4b-uncensored"
    preset = resolve_llamacpp_preset("gemma-4-e4b-uncensored")
    assert "HauhauCS" in preset.label


def test_correction_pass2_openrouter_unchanged(monkeypatch):
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_MODEL", "deepseek/deepseek-v3.2")
    tier = correction_llm_tier(2)
    assert tier["provider"] == "openrouter"
    assert tier["model"] == "deepseek/deepseek-v3.2"
