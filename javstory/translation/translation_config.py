"""Translation engine / llama.cpp server settings from environment."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from javstory.config.app_config import _effective_translation_provider
from javstory.llm.llamacpp_backend import (
    LLAMACPP_GGUF_PATH_ENV,
    LlamaCppServerConfig,
    build_server_argv,
    gguf_scan_dir_from_env,
    is_gguf_option_id,
    list_translation_gguf_model_options,
    llamacpp_bin_path,
    resolve_preset_for_translation,
    resolve_translation_llamacpp_preset_id,
    resolve_translation_llamacpp_runtime,
)

TRANSLATION_PROVIDERS: tuple[str, ...] = ("llamacpp", "openrouter", "ollama")

TRANSLATION_PROVIDER_LABELS: dict[str, str] = {
    "llamacpp": "llama.cpp (로컬 llama-server)",
    "openrouter": "OpenRouter (클라우드 API)",
    "ollama": "Ollama (로컬)",
}

OPENROUTER_PROFILES: tuple[tuple[str, str], ...] = (
    ("default", "DeepSeek V3.2 (기본)"),
    ("keeper", "GLM 5.1 (소장)"),
    ("deepseek_chat", "DeepSeek Chat"),
)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    raw = (os.environ.get(key, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_int_optional(key: str) -> int | None:
    raw = (os.environ.get(key, "") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def normalize_translation_provider(raw: str | None) -> str:
    p = (raw or "llamacpp").strip().lower()
    if p in TRANSLATION_PROVIDERS:
        return p
    if p in ("openai", "gemini"):
        return "openrouter"
    return "llamacpp"


def translation_provider_from_env() -> str:
    return normalize_translation_provider(_effective_translation_provider(None))


def openrouter_profile_from_env() -> str:
    raw = (os.environ.get("JAVSTORY_TRANSLATION_PROFILE", "") or "").strip().lower()
    for pid, _ in OPENROUTER_PROFILES:
        if raw == pid:
            return pid
    if raw in ("keeper", "archive", "premium", "glm", "소장"):
        return "keeper"
    if raw in ("deepseek_chat", "deepseek-chat", "ds_chat"):
        return "deepseek_chat"
    return "default"


def llamacpp_model_from_env() -> str:
    from javstory.llm.llamacpp_backend import resolve_translation_llamacpp_preset_id

    return resolve_translation_llamacpp_preset_id()


def gguf_env_key_for_model(model_id: str) -> str:
    if is_gguf_option_id(model_id):
        return LLAMACPP_GGUF_PATH_ENV
    from javstory.llm.llamacpp_backend import resolve_llamacpp_preset

    return resolve_llamacpp_preset(model_id).gguf_env


def gguf_path_from_env(model_id: str | None = None) -> str:
    direct = (os.environ.get(LLAMACPP_GGUF_PATH_ENV, "") or "").strip()
    if direct:
        return direct
    mid = model_id or llamacpp_model_from_env()
    if is_gguf_option_id(mid):
        from javstory.llm.llamacpp_backend import parse_gguf_option_id

        parsed = parse_gguf_option_id(mid)
        if parsed:
            return str(parsed)
    from javstory.llm.llamacpp_backend import resolve_llamacpp_preset

    preset = resolve_llamacpp_preset(mid)
    return (os.environ.get(preset.gguf_env, "") or "").strip()


def llamacpp_port_from_env() -> int:
    url = (os.environ.get("JAVSTORY_LLAMACPP_URL", "") or "").strip()
    if url:
        parsed = urlparse(url)
        if parsed.port:
            return parsed.port
    return _env_int("JAVSTORY_LLAMACPP_PORT", 8081)


def llamacpp_url_from_env() -> str:
    explicit = (os.environ.get("JAVSTORY_LLAMACPP_URL", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = (os.environ.get("JAVSTORY_LLAMACPP_HOST", "127.0.0.1") or "127.0.0.1").strip()
    return f"http://{host}:{llamacpp_port_from_env()}"


def llamacpp_fit_vram_from_env() -> bool:
    fit_raw = (os.environ.get("JAVSTORY_LLAMACPP_FIT", "on") or "on").strip().lower()
    return fit_raw not in ("0", "false", "off", "no")


def llamacpp_flash_attn_from_env(preset_id: str | None = None) -> bool:
    raw = (os.environ.get("JAVSTORY_LLAMACPP_FLASH_ATTN", "") or "").strip().lower()
    if raw in ("0", "false", "off", "no"):
        return False
    if raw in ("1", "true", "on", "yes"):
        return True
    preset = resolve_preset_for_translation(preset_id or llamacpp_model_from_env())
    return any("flash-attn" in str(a).lower() or a in ("-fa",) for a in preset.extra_args)


def build_llamacpp_command_preview() -> str:
    try:
        runtime = resolve_translation_llamacpp_runtime()
    except FileNotFoundError:
        model = llamacpp_model_from_env()
        preset = resolve_preset_for_translation(model)
        bin_p = llamacpp_bin_path()
        return (
            f"{bin_p} -m <{preset.gguf_env}> -c {preset.default_ctx} "
            f"--port {llamacpp_port_from_env()}"
        )
    cfg = LlamaCppServerConfig.from_env(runtime.preset)
    return " ".join(build_server_argv(runtime.gguf, cfg, runtime.preset))


def llamacpp_settings_snapshot() -> dict[str, Any]:
    model = llamacpp_model_from_env()
    preset = resolve_preset_for_translation(model)
    cfg = LlamaCppServerConfig.from_env(preset)
    ngl = _env_int_optional("JAVSTORY_LLAMACPP_N_GPU_LAYERS")
    if ngl is None and preset.default_ngl >= 0:
        ngl = preset.default_ngl
    ctx = _env_int("JAVSTORY_LLAMACPP_CTX", preset.default_ctx)
    gguf_env = LLAMACPP_GGUF_PATH_ENV if is_gguf_option_id(model) else preset.gguf_env
    return {
        "bin": str(llamacpp_bin_path()),
        "url": llamacpp_url_from_env(),
        "port": llamacpp_port_from_env(),
        "model": model,
        "gguf_path": gguf_path_from_env(model),
        "gguf_env": gguf_env,
        "gguf_scan_dir": str(gguf_scan_dir_from_env()),
        "ctx": ctx,
        "n_gpu_layers": ngl,
        "cache_type_k": (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_K", "turbo3") or "turbo3").strip(),
        "cache_type_v": (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_V", "q8_0") or "q8_0").strip(),
        "threads": _env_int_optional("JAVSTORY_LLAMACPP_THREADS"),
        "tensorcores": _env_bool("JAVSTORY_LLAMACPP_TENSORCORES", False),
        "flash_attn": llamacpp_flash_attn_from_env(model),
        "auto_start": _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True),
        "fit_vram": llamacpp_fit_vram_from_env(),
        "command_preview": build_llamacpp_command_preview(),
    }


def translation_settings_snapshot() -> dict[str, Any]:
    return {
        "provider": translation_provider_from_env(),
        "openrouter_profile": openrouter_profile_from_env(),
        "llamacpp": llamacpp_settings_snapshot(),
        "provider_options": [
            {"id": pid, "label": TRANSLATION_PROVIDER_LABELS.get(pid, pid)}
            for pid in TRANSLATION_PROVIDERS
        ],
        "model_options": list_translation_gguf_model_options(),
        "openrouter_profile_options": [
            {"id": pid, "label": label}
            for pid, label in OPENROUTER_PROFILES
        ],
    }
