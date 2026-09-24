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


def test_harvest_slot_ctx_from_env(monkeypatch):
    from javstory.llm.llamacpp_backend import harvest_slot_ctx_from_env

    monkeypatch.delenv("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", raising=False)
    assert harvest_slot_ctx_from_env() is None
    monkeypatch.setenv("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", "4096")
    assert harvest_slot_ctx_from_env() == 4096


def test_from_env_uses_harvest_slot_ctx(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import LlamaCppServerConfig, resolve_llamacpp_preset

    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("gemma-4-e4b")
    monkeypatch.setenv("JAVSTORY_HARVEST_CONCURRENCY", "5")
    monkeypatch.setenv("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", "4096")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_CTX", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_PARALLEL", raising=False)
    cfg = LlamaCppServerConfig.from_env(preset)
    assert cfg.parallel == 5
    assert cfg.ctx_size == 4096 * 5


def test_gpu_plan_single_gpu_stays_single_even_if_oversized(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import resolve_llamacpp_gpu_plan

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (20 * 1024 * 1024))  # tiny file, size faked via threshold below
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)

    plan = resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is False
    assert plan["cuda_visible_devices"] == "0"


def test_gpu_plan_auto_splits_when_two_gpus_and_over_threshold(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import resolve_llamacpp_gpu_plan

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (200 * 1024 * 1024))  # ~0.195GB > 0.1GB threshold floor
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)

    plan = resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is True
    assert plan["cuda_visible_devices"] == "0,1"
    assert plan["main_gpu"] == 0


def test_gpu_plan_two_gpus_under_threshold_stays_single(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import resolve_llamacpp_gpu_plan

    gguf = tmp_path / "small.gguf"
    gguf.write_bytes(b"x" * 1024)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "12")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)

    plan = resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is False
    assert plan["cuda_visible_devices"] == "0"


def test_gpu_plan_explicit_off_wins_over_auto(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import resolve_llamacpp_gpu_plan

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (20 * 1024 * 1024))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MULTI_GPU", "off")

    plan = resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is False


def test_gpu_plan_explicit_on_forces_split_without_detection(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import resolve_llamacpp_gpu_plan

    gguf = tmp_path / "small.gguf"
    gguf.write_bytes(b"x" * 1024)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MULTI_GPU", "on")

    plan = resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is True
    assert plan["cuda_visible_devices"] == "0,1"


def test_forced_ngl_ignored_when_multi_gpu_split_active(monkeypatch, tmp_path):
    """대형 모델이 듀얼 GPU로 쪼개질 때 JAVSTORY_LLAMACPP_N_GPU_LAYERS 강제값을 그대로
    쓰면 llama.cpp의 fit 검사가 건너뛰어져 VRAM 오버플로 시 시스템 RAM으로 넘쳐서
    (Windows 드라이버 spillover) 극도로 느려진다 — 이 경우엔 -fit에 맡겨야 한다."""
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (200 * 1024 * 1024))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "99")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()

    preset = backend.resolve_llamacpp_preset("qwen3-14b")
    cfg = backend.LlamaCppServerConfig.from_env(preset, gguf)
    assert cfg.multi_gpu is True
    assert cfg.n_gpu_layers is None  # -fit에 맡김, -ngl 99를 강제하지 않음


def test_forced_ngl_still_applies_when_single_gpu(monkeypatch, tmp_path):
    """단일 GPU에 이미 다 들어가는(분할 불필요) 작은 모델에서는 강제값을 존중한다."""
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "small.gguf"
    gguf.write_bytes(b"x" * 1024)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "12")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "99")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()

    preset = backend.resolve_llamacpp_preset("qwen3-14b")
    cfg = backend.LlamaCppServerConfig.from_env(preset, gguf)
    assert cfg.multi_gpu is False
    assert cfg.n_gpu_layers == 99


def test_build_server_argv_includes_reasoning_format_by_default(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "--reasoning-format" in argv
    assert argv[argv.index("--reasoning-format") + 1] == "deepseek"


def test_build_server_argv_reasoning_format_can_be_disabled(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig(reasoning_format="none")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "--reasoning-format" not in argv


def test_server_config_from_env_reads_reasoning_format(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import LlamaCppServerConfig, resolve_llamacpp_preset

    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_REASONING_FORMAT", "none")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig.from_env(preset)
    assert cfg.reasoning_format == "none"


def test_server_config_fingerprint_stable_across_repeated_calls_without_explicit_tensor_split(
    monkeypatch, tmp_path
):
    """tensor_split을 명시하지 않으면 항상 None(지문 "auto")이어야 한다 — 흔들리는
    가짓값을 넣으면 실제로는 설정이 안 바뀌었는데도 매 호출마다 llama-server가
    재시작될 수 있다."""
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (200 * 1024 * 1024))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_TENSOR_SPLIT", raising=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()

    preset = backend.resolve_llamacpp_preset("qwen3-14b")

    cfg1 = backend.LlamaCppServerConfig.from_env(preset, gguf)
    fp1 = backend.server_config_fingerprint(cfg1, gguf)
    cfg2 = backend.LlamaCppServerConfig.from_env(preset, gguf)
    fp2 = backend.server_config_fingerprint(cfg2, gguf)

    assert cfg1.tensor_split is None
    assert cfg2.tensor_split is None
    assert fp1 == fp2


def test_server_config_fingerprint_changes_with_explicit_tensor_split(monkeypatch, tmp_path):
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = backend.resolve_llamacpp_preset("qwen3-14b")
    cfg = backend.LlamaCppServerConfig()

    monkeypatch.setenv("JAVSTORY_LLAMACPP_TENSOR_SPLIT", "1,1")
    fp1 = backend.server_config_fingerprint(cfg, gguf)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_TENSOR_SPLIT", "2,1")
    fp2 = backend.server_config_fingerprint(cfg, gguf)
    assert fp1 != fp2


def test_cleanup_managed_llamacpp_ignores_stop_after_job_flag_on_normal_completion(monkeypatch):
    """JAVSTORY_LLAMACPP_STOP_AFTER_JOB=1(번역/교정용)이 켜져 있어도, 페르소나챗
    정상 완료 시엔 서버를 내리지 않아야 한다(매 턴 VRAM 재로딩 방지)."""
    import javstory.llm.llamacpp_backend as backend

    monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "1")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")
    monkeypatch.delenv("JAVSTORY_PERSONA_CHAT_BASE_URL", raising=False)

    stop_calls: list[bool] = []
    monkeypatch.setattr(backend, "stop_llamacpp_server", lambda **kw: stop_calls.append(True))

    backend.cleanup_managed_llamacpp_after_job(cancelled=False)
    assert stop_calls == []


def test_cleanup_managed_llamacpp_stops_on_explicit_cancel(monkeypatch):
    import javstory.llm.llamacpp_backend as backend

    monkeypatch.setenv("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", "0")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")
    monkeypatch.delenv("JAVSTORY_PERSONA_CHAT_BASE_URL", raising=False)

    stop_calls: list[bool] = []
    monkeypatch.setattr(backend, "stop_llamacpp_server", lambda **kw: stop_calls.append(True))

    backend.cleanup_managed_llamacpp_after_job(cancelled=True)
    assert stop_calls == [True]


def test_build_server_argv_omits_batch_flags_by_default(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert "-b" not in argv
    assert "-ub" not in argv


def test_build_server_argv_includes_batch_flags_when_set(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig(batch_size=2048, ubatch_size=1024)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    (tmp_path / "llama-server.exe").touch()
    argv = build_server_argv(gguf, cfg, preset)
    assert argv[argv.index("-b") + 1] == "2048"
    assert argv[argv.index("-ub") + 1] == "1024"


def test_server_config_from_env_reads_batch_size(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import LlamaCppServerConfig, resolve_llamacpp_preset

    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(tmp_path / "llama-server.exe"))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BATCH_SIZE", "2048")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_UBATCH_SIZE", "1024")
    preset = resolve_llamacpp_preset("qwen3-14b")
    cfg = LlamaCppServerConfig.from_env(preset)
    assert cfg.batch_size == 2048
    assert cfg.ubatch_size == 1024


def test_gpu_plan_tensor_split_none_by_default_lets_fit_decide(monkeypatch, tmp_path):
    """tensor_split을 넘기지 않아야 llama.cpp -fit이 ngl과 GPU 분배 비율을 함께
    계산할 수 있다 — 직접 계산해 넘기면 -fit의 자체 적합성 검사가 건너뛰어져(로그:
    "model_params::tensor_split already set by user, abort") VRAM 오버플로 시
    Windows 드라이버가 시스템 RAM으로 조용히 넘쳐서(spillover) 극도로 느려진다."""
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (200 * 1024 * 1024))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)
    monkeypatch.delenv("JAVSTORY_LLAMACPP_TENSOR_SPLIT", raising=False)

    plan = backend.resolve_llamacpp_gpu_plan(gguf)
    assert plan["multi_gpu"] is True
    assert plan["tensor_split"] is None


def test_gpu_plan_explicit_tensor_split_is_honored(monkeypatch, tmp_path):
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "big.gguf"
    gguf.write_bytes(b"x" * (200 * 1024 * 1024))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "2")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", "0.0001")
    monkeypatch.delenv("JAVSTORY_LLAMACPP_MULTI_GPU", raising=False)
    monkeypatch.setenv("JAVSTORY_LLAMACPP_TENSOR_SPLIT", "2,1")

    plan = backend.resolve_llamacpp_gpu_plan(gguf)
    assert plan["tensor_split"] == "2,1"


def test_build_server_argv_multi_gpu_flags(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    cfg = LlamaCppServerConfig(
        n_gpu_layers=None,
        fit_vram=True,
        multi_gpu=True,
        main_gpu=0,
        tensor_split="1,0.5",
        split_mode="layer",
        cuda_visible_devices="0,1",
    )
    argv = build_server_argv(gguf, cfg, preset)
    assert argv[argv.index("--main-gpu") + 1] == "0"
    assert argv[argv.index("--split-mode") + 1] == "layer"
    assert argv[argv.index("--tensor-split") + 1] == "1,0.5"


def test_build_server_argv_single_gpu_omits_multi_gpu_flags(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("qwen3-14b")
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    cfg = LlamaCppServerConfig(n_gpu_layers=None, fit_vram=True)
    argv = build_server_argv(gguf, cfg, preset)
    assert "--main-gpu" not in argv
    assert "--tensor-split" not in argv


def test_llamacpp_child_env_sets_cuda_visible_devices(monkeypatch):
    from javstory.llm.llamacpp_backend import LlamaCppServerConfig, _llamacpp_child_env

    cfg = LlamaCppServerConfig(cuda_visible_devices="0,1")
    env = _llamacpp_child_env(cfg)
    assert env["CUDA_VISIBLE_DEVICES"] == "0,1"
    assert env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_server_config_fingerprint_changes_with_parallel(monkeypatch, tmp_path):
    from javstory.llm.llamacpp_backend import (
        LlamaCppServerConfig,
        resolve_llamacpp_preset,
        server_config_fingerprint,
    )

    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"x")
    preset = resolve_llamacpp_preset("gemma-4-e4b")
    cfg1 = LlamaCppServerConfig(parallel=3, ctx_size=12288)
    cfg2 = LlamaCppServerConfig(parallel=5, ctx_size=20480)
    assert server_config_fingerprint(cfg1, gguf) != server_config_fingerprint(cfg2, gguf)


def test_get_active_llamacpp_requests_reflects_begin_end():
    import javstory.llm.llamacpp_backend as backend

    backend._active_requests = 0
    assert backend.get_active_llamacpp_requests() == 0
    backend.begin_llamacpp_request()
    backend.begin_llamacpp_request()
    assert backend.get_active_llamacpp_requests() == 2
    backend.end_llamacpp_request()
    assert backend.get_active_llamacpp_requests() == 1
    backend.end_llamacpp_request()
    assert backend.get_active_llamacpp_requests() == 0


def test_wait_for_llamacpp_idle_returns_immediately_when_idle():
    import javstory.llm.llamacpp_backend as backend

    backend._active_requests = 0
    assert backend._wait_for_llamacpp_idle(timeout=5.0, logger_func=lambda _m: None) is True


def test_wait_for_llamacpp_idle_times_out_when_busy():
    import javstory.llm.llamacpp_backend as backend
    import time as _time

    backend._active_requests = 1
    try:
        start = _time.time()
        ok = backend._wait_for_llamacpp_idle(
            timeout=0.3, poll_interval=0.05, logger_func=lambda _m: None
        )
        elapsed = _time.time() - start
        assert ok is False
        assert elapsed >= 0.3
    finally:
        backend._active_requests = 0


def test_swap_path_waits_for_idle_before_terminating(monkeypatch, tmp_path):
    """Model-swap (different runtime_id already tracked) must wait for
    in-flight requests before killing the old process, never kill first."""
    import javstory.llm.llamacpp_backend as backend

    gguf = tmp_path / "Qwen3-14B.gguf"
    gguf.write_bytes(b"x")
    bin_p = tmp_path / "llama-server.exe"
    bin_p.touch()
    monkeypatch.setenv("JAVSTORY_LLAMACPP_BIN", str(bin_p))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_QWEN3_14B_GGUF", str(gguf))
    monkeypatch.setenv("JAVSTORY_LLAMACPP_AUTO_START", "1")

    fake_proc = type(
        "P", (), {"poll": lambda self: None, "pid": 4242}
    )()
    backend._server_proc = fake_proc
    backend._active_preset_id = "gemma-4-e4b"  # different from requested "qwen3-14b"
    backend._active_requests = 0

    call_order: list[str] = []
    monkeypatch.setattr(
        backend,
        "_wait_for_llamacpp_idle",
        lambda *a, **kw: call_order.append("wait") or True,
    )
    monkeypatch.setattr(
        backend,
        "_terminate_llamacpp_proc",
        lambda *a, **kw: call_order.append("terminate"),
    )
    # Stop the flow right after the kill decision so we don't need a real spawn.
    monkeypatch.setattr(backend, "_server_health_ok", lambda *a, **kw: False)
    monkeypatch.setattr(
        backend,
        "_spawn_server",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("stop-here")),
    )

    with pytest.raises(RuntimeError, match="stop-here"):
        backend.ensure_llamacpp_server_ready({"model": "qwen3-14b"})

    assert call_order == ["wait", "terminate"]


def test_llamacpp_server_status_states(monkeypatch, tmp_path):
    import javstory.llm.llamacpp_backend as backend

    backend._server_proc = None
    backend._active_preset_id = None
    backend._spawning = False
    backend._active_requests = 0
    status = backend.llamacpp_server_status()
    assert status["state"] == "stopped"

    backend._spawning = True
    status = backend.llamacpp_server_status()
    assert status["state"] == "spawning"
    backend._spawning = False

    fake_proc = type("P", (), {"poll": lambda self: None})()
    backend._server_proc = fake_proc
    backend._active_preset_id = "qwen3-14b"
    backend._active_requests = 0
    status = backend.llamacpp_server_status()
    assert status["state"] == "ready"
    assert status["active_preset_id"] == "qwen3-14b"
    assert status["active_label"] == LLAMACPP_MODEL_PRESETS["qwen3-14b"].label

    backend._active_requests = 2
    status = backend.llamacpp_server_status()
    assert status["state"] == "busy"

    backend._server_proc = None
    backend._active_preset_id = None
    backend._active_requests = 0
