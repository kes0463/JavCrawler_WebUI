"""Prompt loader for versioned Persona Chat system prompts."""

from __future__ import annotations

from typing import Type

from javstory.persona.prompts.base_system_prompt import BaseSystemPrompt
from javstory.persona.prompts.v1_cot_prompt import V1CoTPrompt

_PROMPT_REGISTRY: dict[str, Type[BaseSystemPrompt]] = {
    "base": BaseSystemPrompt,
    "v1": V1CoTPrompt,
}


def get_prompt(version: str) -> Type[BaseSystemPrompt]:
    """Return the prompt class for a version string."""
    key = (version or "v1").strip().lower()
    try:
        return _PROMPT_REGISTRY[key]
    except KeyError as exc:
        available = ", ".join(sorted(_PROMPT_REGISTRY))
        raise ValueError(f"Unknown persona prompt version: {version!r}. Available: {available}") from exc
