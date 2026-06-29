"""Harvest / subtitle translation default tier tests."""

from __future__ import annotations

import os

import pytest


def test_harvest_translation_default_is_llamacpp_gemma(monkeypatch):
    monkeypatch.delenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", raising=False)
    from javstory.config.app_config import harvest_translation_llm_tier

    tier = harvest_translation_llm_tier()
    assert tier["provider"] == "llamacpp"
    assert tier.get("llamacpp_preset") == "gemma-4-e4b"


def test_effective_translation_provider_budget_is_llamacpp(monkeypatch):
    monkeypatch.delenv("JAVSTORY_TRANSLATION_PROVIDER", raising=False)
    monkeypatch.delenv("JAVSTORY_LLM_PLATFORM", raising=False)
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    from javstory.config.app_config import _effective_translation_provider

    assert _effective_translation_provider(None) == "llamacpp"


def test_harvest_translation_uses_platform_specific_env(monkeypatch):
    monkeypatch.setenv("JAVSTORY_LLM_PLATFORM", "llamacpp")
    monkeypatch.delenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", raising=False)
    monkeypatch.setenv(
        "JAVSTORY_HARVEST_TRANSLATION_MODEL_LLAMACPP",
        "llamacpp:gemma-4-e4b",
    )
    from javstory.config.app_config import harvest_translation_llm_tier

    tier = harvest_translation_llm_tier()
    assert tier["provider"] == "llamacpp"
    assert tier.get("llamacpp_preset") == "gemma-4-e4b"


def test_ensure_project_env_loads_llamacpp_turboquant(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JAVSTORY_LLM_PLATFORM=llamacpp\n"
        "JAVSTORY_LLAMACPP_MODEL=gemma-4-e4b\n"
        "JAVSTORY_LLAMACPP_CACHE_TYPE_K=turbo3\n"
        "JAVSTORY_LLAMACPP_CACHE_TYPE_V=q8_0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "javstory.config.app_config.ENV_FILE_PATH",
        env_file,
        raising=False,
    )
    monkeypatch.setattr("javstory.config.app_config._env_file_loaded", False, raising=False)
    from javstory.config import app_config

    app_config.ensure_project_env_loaded()
    assert os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_K") == "turbo3"
    assert os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_V") == "q8_0"
    from javstory.llm.llamacpp_backend import LlamaCppServerConfig, resolve_llamacpp_preset

    cfg = LlamaCppServerConfig.from_env(resolve_llamacpp_preset("gemma-4-e4b"))
    assert cfg.cache_type_k == "turbo3"
    assert cfg.cache_type_v == "q8_0"
