"""llama.cpp + TurboQuant 백엔드."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from javstory.llm.llamacpp_backend import (
    LLAMACPP_DEFAULT_CTX_MOE,
    LLAMACPP_DEFAULT_MAX_TOKENS,
    LLAMACPP_DEFAULT_N_CPU_MOE,
    LLAMACPP_DEFAULT_PROMPT_CACHE_MIB,
    LLAMACPP_MODEL_PRESETS,
    LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB,
    LlamaCppServerConfig,
    build_server_argv,
    cleanup_llamacpp_after_job,
    llamacpp_max_tokens_from_env,
    llamacpp_n_cpu_moe_for_spawn,
    resolve_active_llamacpp_preset_id,
    resolve_llamacpp_preset,
    tier_from_llamacpp_env,
)


def test_resolve_preset_aliases():
    p = resolve_llamacpp_preset("gemma")
    assert p.id == "gemma-4-e4b"
    p2 = resolve_llamacpp_preset("qwen3.5-35b-a3b")
    assert p2.moe is True


def test_build_server_argv_turboquant(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3.5-35b-a3b")
    cfg = LlamaCppServerConfig(
        host="127.0.0.1",
        port=8081,
        cache_type_k="turbo3",
        cache_type_v="q8_0",
        n_gpu_layers=None,
        ctx_size=8192,
        fit_vram=True,
    )
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))

    argv = build_server_argv(gguf, cfg, preset)
    assert "-ctk" in argv
    assert "turbo3" in argv
    assert "-ctv" in argv
    assert "q8_0" in argv
    assert "-m" in argv
    assert str(gguf) in argv
    assert "-fit" in argv
    assert "on" in argv
    assert "-ngl" not in argv
    assert "--cache-ram" in argv
    assert argv[argv.index("--cache-ram") + 1] == str(LLAMACPP_DEFAULT_PROMPT_CACHE_MIB)


def test_build_server_argv_explicit_ngl(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("gemma-4-e4b")
    cfg = LlamaCppServerConfig(n_gpu_layers=40, fit_vram=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "-ngl" in argv
    assert "40" in argv
    assert "-fit" not in argv


def test_tier_from_env(monkeypatch):
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "gemma-4-e4b")
    tier = tier_from_llamacpp_env()
    assert tier["provider"] == "llamacpp"
    assert tier["llamacpp_preset"] == "gemma-4-e4b"


def test_resolve_translation_llm_tier_llamacpp_platform(monkeypatch):
    from javstory.config.app_config import resolve_translation_llm_tier

    monkeypatch.setenv("JAVSTORY_LLM_PLATFORM", "llamacpp")
    tier = resolve_translation_llm_tier()
    assert tier["provider"] == "llamacpp"


def test_presets_cover_required_models():
    assert "qwen3.5-35b-a3b" in LLAMACPP_MODEL_PRESETS
    assert "gemma-4-e4b" in LLAMACPP_MODEL_PRESETS
    assert "qwen3.5-35b-a3b-uncensored" in LLAMACPP_MODEL_PRESETS
    assert "gemma-4-e4b-uncensored" in LLAMACPP_MODEL_PRESETS


def test_uncensored_preset_low_ram_defaults():
    p = resolve_llamacpp_preset("qwen3.5-35b-a3b-uncensored")
    assert p.default_ctx == LLAMACPP_DEFAULT_CTX_MOE
    assert p.default_ctx == 4096


def test_max_tokens_default(monkeypatch):
    monkeypatch.delenv("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", raising=False)
    monkeypatch.delenv("JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS", raising=False)
    assert llamacpp_max_tokens_from_env(correction=True) == LLAMACPP_DEFAULT_MAX_TOKENS


def test_build_server_argv_prompt_cache_from_env(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3.5-35b-a3b")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_PROMPT_CACHE_MB", "8192")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    cfg = LlamaCppServerConfig.from_env(preset)
    argv = build_server_argv(gguf, cfg, preset)
    assert argv[argv.index("--cache-ram") + 1] == str(LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB)


def test_cleanup_llamacpp_on_cancel_always_stops(monkeypatch):
  calls: list[bool] = []

  def _fake_stop(**_kwargs):
      calls.append(True)

  monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "0")
  monkeypatch.setattr(
      "javstory.llm.llamacpp_backend.stop_llamacpp_server",
      lambda **kw: _fake_stop(**kw),
  )
  cleanup_llamacpp_after_job(cancelled=True)
  assert len(calls) == 1


def test_cleanup_llamacpp_respects_stop_after_job(monkeypatch):
  calls: list[bool] = []

  monkeypatch.setattr(
      "javstory.llm.llamacpp_backend.stop_llamacpp_server",
      lambda **kw: calls.append(True),
  )
  monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "0")
  cleanup_llamacpp_after_job(cancelled=False)
  assert calls == []
  monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "1")
  cleanup_llamacpp_after_job(cancelled=False)
  assert len(calls) == 1


def test_resolve_active_llamacpp_preset_unifies_correction_over_model(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3.5-35b-a3b")
    monkeypatch.setenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", "llamacpp:gemma-4-e4b")
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    assert resolve_active_llamacpp_preset_id() == "gemma-4-e4b-uncensored"


def test_resolve_active_llamacpp_from_translation_profile_budget(monkeypatch):
    monkeypatch.delenv("JAVSTORY_CORRECTION_PASS2_MODEL", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MODEL", raising=False)
    monkeypatch.delenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", raising=False)
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    assert resolve_active_llamacpp_preset_id() == "gemma-4-e4b"


def test_tier_from_env_uses_active_preset(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3.5-35b-a3b")
    tier = tier_from_llamacpp_env()
    assert tier["llamacpp_preset"] == "gemma-4-e4b-uncensored"
    assert "qwen" not in (tier.get("model") or "").lower() or "uncensored" in tier["llamacpp_preset"]


def test_moe_n_cpu_moe_default_and_disable(monkeypatch):
    monkeypatch.delenv("JAVSTORY_LLAMACPP_N_CPU_MOE", raising=False)
    assert llamacpp_n_cpu_moe_for_spawn(preset_moe=True) == LLAMACPP_DEFAULT_N_CPU_MOE
    assert llamacpp_n_cpu_moe_for_spawn(preset_moe=False) is None
    monkeypatch.setenv("JAVSTORY_LLAMACPP_N_CPU_MOE", "0")
    assert llamacpp_n_cpu_moe_for_spawn(preset_moe=True) is None
    monkeypatch.setenv("JAVSTORY_LLAMACPP_N_CPU_MOE", "16")
    assert llamacpp_n_cpu_moe_for_spawn(preset_moe=True) == 16


def test_build_server_argv_moe_has_n_cpu_moe(monkeypatch, tmp_path):
    gguf = tmp_path / "Qwen3.5-35B-A3B.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3.5-35b-a3b-uncensored")
    assert preset.moe is True
    cfg = LlamaCppServerConfig(ctx_size=4096, n_gpu_layers=None, fit_vram=True)
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    monkeypatch.delenv("JAVSTORY_LLAMACPP_N_CPU_MOE", raising=False)
    argv = build_server_argv(gguf, cfg, preset)
    assert "--n-cpu-moe" in argv
    assert argv[argv.index("--n-cpu-moe") + 1] == str(LLAMACPP_DEFAULT_N_CPU_MOE)
    assert "--ctx-size" not in argv
    assert argv[argv.index("-c") + 1] == "4096"


def test_build_server_argv_gemma_no_n_cpu_moe(monkeypatch, tmp_path):
    gguf = tmp_path / "gemma.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("gemma-4-e4b")
    assert preset.moe is False
    cfg = LlamaCppServerConfig()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "--n-cpu-moe" not in argv


def test_build_server_argv_moe_ctx_4096(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3.5-35b-a3b-uncensored")
    cfg = LlamaCppServerConfig(ctx_size=4096, n_gpu_layers=None, fit_vram=True)
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    argv = build_server_argv(gguf, cfg, preset)
    assert "-c" in argv
    assert "4096" in argv
    assert "--parallel" in argv
    idx = argv.index("--parallel")
    assert argv[idx + 1] == "1"
