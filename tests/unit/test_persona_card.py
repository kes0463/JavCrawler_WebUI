"""persona_card.py 모델 선택 매퍼 및 llama-server 정리 동작."""

from __future__ import annotations

from unittest.mock import patch

from javstory.analytics.persona_card import (
    persona_card_model_from_env,
    persona_card_model_from_env_value,
)


def test_persona_card_model_from_env_passes_through_exact_preset_id(monkeypatch):
    monkeypatch.setenv("JAVSTORY_PERSONA_CARD_PRESET", "qwen38-27b-unsloth")
    assert persona_card_model_from_env() == "qwen38-27b-unsloth"


def test_persona_card_model_from_env_strips_llamacpp_prefix_for_exact_id(monkeypatch):
    monkeypatch.setenv("JAVSTORY_PERSONA_CARD_PRESET", "llamacpp:gemma4-31b-uncensored")
    assert persona_card_model_from_env() == "gemma4-31b-uncensored"


def test_persona_card_model_from_env_legacy_loose_values_still_degrade(monkeypatch):
    monkeypatch.delenv("JAVSTORY_PERSONA_CARD_PRESET", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_PRESET", raising=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3-14b-instruct-whatever")
    assert persona_card_model_from_env() == "qwen3-14b"


def test_persona_card_model_from_env_value_exact_passthrough():
    assert persona_card_model_from_env_value("qwen38-27b-unsloth") == "qwen38-27b-unsloth"


def test_persona_card_model_from_env_value_legacy_bucket_unchanged():
    assert persona_card_model_from_env_value("qwen3.5-something-a3b") == "legacy-qwen35-a3b"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_synthesize_persona_v3_does_not_stop_server_when_stop_after_job_flag_set(monkeypatch):
    """Insight 새로고침이 매번 llama-server를 재로딩하지 않도록, 페르소나 카드 합성도
    번역/교정 배치용 JAVSTORY_LLAMACPP_STOP_AFTER_JOB 플래그를 무시해야 한다."""
    import javstory.llm.llamacpp_backend as backend
    from javstory.analytics.persona_card import synthesize_persona_v3

    monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")
    monkeypatch.delenv("JAVSTORY_PERSONA_CHAT_BASE_URL", raising=False)
    monkeypatch.setattr(backend, "ensure_llamacpp_server_ready", lambda *a, **kw: "model")
    monkeypatch.setattr(backend, "llamacpp_openai_base_url", lambda: "http://127.0.0.1:8081/v1")

    stop_calls: list[bool] = []
    monkeypatch.setattr(backend, "stop_llamacpp_server", lambda **kw: stop_calls.append(True))

    fake_json = {
        "choices": [
            {
                "message": {
                    "content": '{"persona_type":"x","summary":"y","sensual_summary":"","'
                    'drift_note":"","affinities":[],"turn_ons":[],"avoidances":[],"evidence":[]}'
                }
            }
        ]
    }
    with patch("httpx.post", return_value=_FakeResponse(fake_json)):
        payload = synthesize_persona_v3({"stats": {}, "sample_codes": []})

    assert payload["source"] == "llamacpp"
    assert stop_calls == []
