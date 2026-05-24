"""Base prompt template for Persona Chat system prompts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseSystemPrompt:
    """Renders a versioned Persona Chat system prompt."""

    persona_name: str = "JAVSTORY Persona"
    focused_user_context: str = ""
    retrieved_memories: str = ""

    template: str = """\
You are {persona_name}, a JAVSTORY Persona Chat assistant.

Focused user context:
{focused_user_context}

Retrieved memories:
{retrieved_memories}

Answer in Korean. Use the supplied context and memories as grounding signals,
but do not fabricate facts that are not present in the retrieved data.
"""

    def render(
        self,
        *,
        persona_name: str | None = None,
        focused_user_context: str | None = None,
        retrieved_memories: str | None = None,
    ) -> str:
        """Render the prompt with explicit values or instance defaults."""
        return self.template.format(
            persona_name=persona_name if persona_name is not None else self.persona_name,
            focused_user_context=(
                focused_user_context
                if focused_user_context is not None
                else self.focused_user_context
            ),
            retrieved_memories=(
                retrieved_memories
                if retrieved_memories is not None
                else self.retrieved_memories
            ),
        ).strip()
