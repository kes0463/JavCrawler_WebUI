"""llama.cpp + TurboQuant 백엔드."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from javstory.llm.llamacpp_backend import (
    LLAMACPP_DEFAULT_MAX_TOKENS,
    LLAMACPP_DEFAULT_PROMPT_CACHE_MIB,
    LLAMACPP_MODEL_PRESETS,
    LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB,
    LlamaCppServerConfig,
    build_server_argv,
    cleanup_llamacpp_after_job,
    llamacpp_max_tokens_from_env,
    resolve_active_llamacpp_preset_id,
    resolve_llamacpp_preset,
    tier_from_llamacpp_env,
)


def test_resolve_preset_aliases():
    p = resolve_llamacpp_preset("gemma")
    assert p.id == "gemma-4-e4b"
    p2 = resolve_llamacpp_preset("qwen")
    assert p2.id == "qwen3-14b"


def test_build_server_argv_turboquant(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
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
    assert "gemma-4-e4b" in LLAMACPP_MODEL_PRESETS
    assert "qwen3-14b" in LLAMACPP_MODEL_PRESETS
    assert "gemma-4-e4b-uncensored" in LLAMACPP_MODEL_PRESETS
    assert "qwen3-14b-uncensored" in LLAMACPP_MODEL_PRESETS


def test_qwen14_uncensored_preset_dense_defaults():
    p = resolve_llamacpp_preset("qwen3-14b-uncensored")
    assert p.default_ctx == 8192


def test_max_tokens_default(monkeypatch):
    monkeypatch.delenv("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", raising=False)
    monkeypatch.delenv("JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS", raising=False)
    assert llamacpp_max_tokens_from_env(correction=True) == LLAMACPP_DEFAULT_MAX_TOKENS


def test_build_server_argv_prompt_cache_from_env(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
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


def test_stop_llamacpp_server_terminates_registered_loading_process(monkeypatch):
    from javstory.llm import llamacpp_backend as backend

    calls: list[str] = []

    class DummyProc:
        pid = 12345

        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            calls.append(f"wait:{timeout}")

    proc = DummyProc()
    monkeypatch.setattr(backend, "_server_proc", proc)
    monkeypatch.setattr(backend, "_active_preset_id", "gemma-4-e4b")
    monkeypatch.setattr(backend, "_active_requests", 2)

    backend.stop_llamacpp_server(logger_func=lambda _msg: None)

    assert calls == ["terminate", "wait:15"]
    assert backend._server_proc is None
    assert backend._active_preset_id is None
    assert backend._active_requests == 0


def test_ensure_llamacpp_reuses_existing_healthy_server(monkeypatch, tmp_path):
    from javstory.llm import llamacpp_backend as backend

    gguf = tmp_path / "gemma.gguf"
    gguf.write_bytes(b"x")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "gemma-4-e4b")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GEMMA4_GGUF", str(gguf))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")
    monkeypatch.setattr(backend, "_server_proc", None)
    monkeypatch.setattr(backend, "_active_preset_id", None)
    monkeypatch.setattr(backend, "_server_health_ok", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(backend, "_server_model_ids", lambda *_args, **_kwargs: ["gemma-4-e4b"])
    monkeypatch.setattr(
        backend,
        "_spawn_server",
        lambda *_args, **_kwargs: pytest.fail("healthy existing server should be reused"),
    )

    alias = backend.ensure_llamacpp_server_ready({"model": "gemma-4-e4b"}, logger_func=lambda _msg: None)

    assert alias == "gemma-4-e4b"


def test_resolve_translation_llamacpp_preset_ignores_correction_pass2(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen2.5-14b")
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "llamacpp:qwen2.5-14b")
    from javstory.llm.llamacpp_backend import resolve_translation_llamacpp_preset_id

    assert resolve_translation_llamacpp_preset_id() == "qwen2.5-14b"
    tier = tier_from_llamacpp_env()
    assert tier["llamacpp_preset"] == "qwen2.5-14b"
    assert tier["model"] == "qwen2.5-14b"


def test_resolve_active_llamacpp_preset_unifies_correction_over_model(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3-14b")
    monkeypatch.setenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", "llamacpp:gemma-4-e4b")
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    assert resolve_active_llamacpp_preset_id() == "gemma-4-e4b-uncensored"


def test_resolve_active_llamacpp_from_translation_profile_budget(monkeypatch):
    monkeypatch.delenv("JAVSTORY_CORRECTION_PASS2_MODEL", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MODEL", raising=False)
    monkeypatch.delenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", raising=False)
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    assert resolve_active_llamacpp_preset_id() == "gemma-4-e4b"


def test_tier_from_env_uses_translation_preset_not_correction(monkeypatch):
    monkeypatch.setenv(
        "JAVSTORY_CORRECTION_PASS2_MODEL",
        "llamacpp:gemma-4-e4b-uncensored",
    )
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3-14b")
    tier = tier_from_llamacpp_env()
    assert tier["llamacpp_preset"] == "qwen3-14b"
    assert tier["model"] == "qwen3-14b"


def test_build_server_argv_qwen14_has_no_moe_args(monkeypatch, tmp_path):
    gguf = tmp_path / "Qwen3-14B.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b-uncensored")
    cfg = LlamaCppServerConfig(ctx_size=8192, n_gpu_layers=None, fit_vram=True)
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    argv = build_server_argv(gguf, cfg, preset)
    assert "--n-cpu-moe" not in argv
    assert "--moe" not in argv
    assert "--alias" in argv
    assert argv[argv.index("--alias") + 1] == "qwen3-14b-uncensored"


def test_ensure_llamacpp_server_rejects_mismatched_external_model(monkeypatch, tmp_path):
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "Qwen3-14B.gguf"
    gguf.write_bytes(b"x")
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_QWEN3_14B_GGUF", str(gguf))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "qwen3-14b")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")
    backend._server_proc = None
    backend._active_preset_id = None

    class Resp:
        status_code = 200

        def __init__(self, payload=None):
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, timeout=2.0):
        if str(url).endswith("/v1/models"):
            return Resp({"data": [{"id": "gemma-4-e4b"}]})
        return Resp()

    monkeypatch.setattr(backend.httpx, "get", fake_get)

    import pytest

    with pytest.raises(RuntimeError, match="다른 llama-server 모델"):
        backend.ensure_llamacpp_server_ready({"model": "qwen3-14b"})


def test_build_server_argv_gemma_no_n_cpu_moe(monkeypatch, tmp_path):
    gguf = tmp_path / "gemma.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("gemma-4-e4b")
    cfg = LlamaCppServerConfig()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "--n-cpu-moe" not in argv


def test_build_server_argv_qwen14_ctx(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b-uncensored")
    cfg = LlamaCppServerConfig(ctx_size=8192, n_gpu_layers=None, fit_vram=True)
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    argv = build_server_argv(gguf, cfg, preset)
    assert "-c" in argv
    assert "8192" in argv
    assert "--parallel" in argv
    idx = argv.index("--parallel")
    assert argv[idx + 1] == "1"


def test_maybe_idle_shutdown_after_timeout(monkeypatch):
    import javstory.llm.llamacpp_backend as backend
    import time

    calls: list[int] = []

    monkeypatch.setenv("JAVSTORY_LLAMACPP_IDLE_SHUTDOWN", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_IDLE_TIMEOUT_SEC", "30")
    monkeypatch.setattr(
        backend,
        "_kill_port_owner_windows",
        lambda port, **kw: calls.append(port) or True,
    )
    monkeypatch.setattr(backend, "_port_is_listening_netstat", lambda _port: True)

    backend._server_proc = None
    backend._idle_managed_port = 8081
    backend._active_preset_id = "gemma-4-e4b"
    backend._active_requests = 0
    backend._last_activity_at = time.time() - 120

    assert backend._maybe_idle_shutdown(logger_func=lambda _m: None) is True
    assert calls == [8081]
    assert backend._idle_managed_port is None


def test_discover_gguf_models_scans_recursively(tmp_path, monkeypatch):
    from javstory.llm.llamacpp_backend import discover_gguf_models, gguf_option_id

    sub = tmp_path / "qwen"
    sub.mkdir()
    a = sub / "Qwen2.5-14B.gguf"
    b = tmp_path / "gemma.gguf"
    a.write_bytes(b"x")
    b.write_bytes(b"x")

    found = discover_gguf_models(scan_dir=tmp_path)
    assert len(found) == 2
    assert found[0]["label"] == "gemma.gguf"
    assert found[1]["label"] == "Qwen2.5-14B.gguf"
    assert found[1]["id"] == gguf_option_id(a)
    assert found[1]["gguf_path"] == str(a.resolve())


def test_resolve_translation_gguf_path_from_gguf_model_id(tmp_path, monkeypatch):
    from javstory.llm.llamacpp_backend import (
        gguf_option_id,
        resolve_translation_gguf_path,
        resolve_translation_llamacpp_preset_id,
    )

    gguf = tmp_path / "Qwen2.5-14B-Instruct-Q5_K_M.gguf"
    gguf.write_bytes(b"x")
    gid = gguf_option_id(gguf)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", gid)

    assert resolve_translation_llamacpp_preset_id() == gid
    assert resolve_translation_gguf_path() == gguf.resolve()


def test_tier_from_env_uses_gguf_alias(tmp_path, monkeypatch):
    from javstory.llm.llamacpp_backend import gguf_option_id, tier_from_llamacpp_env

    gguf = tmp_path / "Qwen2.5-14B-Instruct-Q5_K_M.gguf"
    gguf.write_bytes(b"x")
    gid = gguf_option_id(gguf)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", gid)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GGUF_PATH", str(gguf))

    tier = tier_from_llamacpp_env()
    assert tier["llamacpp_preset"] == gid
    assert tier["model"] == "Qwen2.5-14B-Instruct-Q5_K_M"
