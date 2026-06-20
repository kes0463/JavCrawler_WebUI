from __future__ import annotations

import sys


def test_llamacpp_active_model_syncs_translation_models(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from gui.models.settings_model import SettingsModel

    monkeypatch.setenv("JAVSTORY_LLM_PLATFORM", "llamacpp")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_MODEL", "gemma-4-e4b-uncensored")
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROFILE", "budget")
    monkeypatch.setenv("JAVSTORY_HARVEST_TRANSLATION_MODEL", "llamacpp:gemma-4-e4b")
    monkeypatch.setenv("JAVSTORY_CORRECTION_PASS2_MODEL", "llamacpp:gemma-4-e4b-uncensored")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_CTX", "8192")

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app
    model = SettingsModel()

    assert model.llamacppModel == "gemma-4-e4b"

    model.llamacppModel = "qwen3-14b"

    assert model.llamacppModel == "qwen3-14b"
    assert model.translationProfile == "qwen3_14"
    assert model.harvestTranslationModel == "llamacpp:qwen3-14b"
    assert model.correctionProfile == "llamacpp:qwen3-14b-uncensored"
    assert model.llamacppCtx == "8192"
