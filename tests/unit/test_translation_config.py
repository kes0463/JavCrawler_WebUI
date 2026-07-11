"""Unit tests for translation engine config."""

from __future__ import annotations

import pytest

from javstory.translation.translation_config import (
    normalize_translation_provider,
    translation_settings_snapshot,
)


def test_normalize_translation_provider() -> None:
    assert normalize_translation_provider("llamacpp") == "llamacpp"
    assert normalize_translation_provider("openai") == "openrouter"
    assert normalize_translation_provider("unknown") == "llamacpp"


def test_translation_settings_snapshot_uses_translation_model_not_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_MODEL", "llamacpp:gemma-4-e4b-uncensored")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen2.5-14b")
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "llamacpp:qwen2.5-14b")
    snap = translation_settings_snapshot()
    assert snap["llamacpp"]["model"] == "qwen2.5-14b"


def test_translation_settings_snapshot_shape(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from javstory.llm.llamacpp_backend import gguf_option_id

    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GGUF_SCAN_DIR", str(tmp_path))
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROVIDER", "llamacpp")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", gguf_option_id(gguf))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GGUF_PATH", str(gguf))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_CTX", "16384")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "99")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_THREADS", "12")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_TENSORCORES", "1")
    snap = translation_settings_snapshot()
    assert snap["provider"] == "llamacpp"
    assert snap["llamacpp"]["model"] == gguf_option_id(gguf)
    assert snap["llamacpp"]["gguf_path"] == str(gguf)
    assert snap["llamacpp"]["ctx"] == 16384
    assert snap["llamacpp"]["n_gpu_layers"] == 99
    assert snap["llamacpp"]["threads"] == 12
    assert snap["llamacpp"]["tensorcores"] is True
    assert len(snap["model_options"]) == 1
    assert snap["model_options"][0]["gguf_path"] == str(gguf.resolve())
