"""persona_chat.py 모델 선택 매퍼 — 정확한 preset id는 그대로 통과해야 한다."""

from __future__ import annotations

from javstory.persona.persona_chat import persona_chat_model_from_env


def test_persona_chat_model_from_env_passes_through_exact_preset_id():
    assert persona_chat_model_from_env("qwen36-35b-a3b-uncensored") == "qwen36-35b-a3b-uncensored"


def test_persona_chat_model_from_env_strips_llamacpp_prefix_for_exact_id():
    assert persona_chat_model_from_env("llamacpp:qwen38-27b-obliterated") == "qwen38-27b-obliterated"


def test_persona_chat_model_from_env_legacy_loose_values_still_degrade():
    assert persona_chat_model_from_env("qwen3-14b-something") == "qwen3-14b-uncensored"
    assert persona_chat_model_from_env("gemma-whatever") == "gemma-4-e4b-uncensored"
