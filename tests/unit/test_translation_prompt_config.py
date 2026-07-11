"""Unit tests for translation prompt configuration."""

from __future__ import annotations

import pytest

from javstory.translation.translation_prompt_config import (
    build_translation_system_prompt,
    format_system_prompt,
    normalize_prompt_mode,
    uses_html_translation_prompt,
)


def test_format_system_prompt_note_placeholders() -> None:
    tpl = "hello {{note}} and {note}"
    assert format_system_prompt(tpl, "X") == "hello X and X"


def test_normalize_prompt_mode() -> None:
    assert normalize_prompt_mode("html") == "html"
    assert normalize_prompt_mode("unknown") == "auto"


def test_uses_html_translation_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROMPT_MODE", "html")
    assert uses_html_translation_prompt({"provider": "llamacpp"}) is True
    monkeypatch.setenv("JAVSTORY_TRANSLATION_PROMPT_MODE", "auto")
    assert uses_html_translation_prompt({"provider": "llamacpp"}) is False
    assert uses_html_translation_prompt({"provider": "gemini"}) is True


def test_build_translation_system_prompt_general_contains_rules() -> None:
    out = build_translation_system_prompt("테스트 노트", variant="general")
    assert "[공리]" in out
    assert "테스트 노트" in out
    assert "HTML" in out
