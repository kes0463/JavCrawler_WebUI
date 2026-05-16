"""핵심 모듈 import smoke — GPU·Whisper·Qt 앱 부트 없이."""

from __future__ import annotations

import importlib

import pytest

# torch/stable-ts/PySide6/gui.app 등 무거운 스택은 제외
SMOKE_MODULES = [
    "javstory.config.app_config",
    "javstory.config.secrets_manager",
    "javstory.library.canonical.schema",
    "javstory.library.detail_persist",
    "javstory.library.video_discovery",
    "javstory.library.media_parts",
    "javstory.library.service",
    "javstory.llm.engine",
    "javstory.harvest.database",
    "javstory.harvest.product_repository",
    "gui.library_data",
    "javstory.pipeline.orchestrator",
    "javstory.translation.story_grok_module",
    "javstory.utils.product_code",
    "gui.library_data",
    "gui.models.library.detail_service",
    "gui.models.library.folder_bind",
    "gui.models.library.search",
    "gui.models.library.sort_filter",
]


@pytest.mark.smoke
@pytest.mark.parametrize("module", SMOKE_MODULES)
def test_import_smoke(module: str) -> None:
    importlib.import_module(module)
