"""Version 2 Persona Chat prompt — 역할 정의만 담고, 컨텍스트/메모리/규칙은 build_messages()가 주입."""

from __future__ import annotations

from dataclasses import dataclass

from javstory.persona.prompts.base_system_prompt import BaseSystemPrompt


@dataclass(frozen=True)
class V2CompactPrompt(BaseSystemPrompt):
    """역할 정의만 담는 최소 프롬프트. 취향 컨텍스트·메모리·응답 규칙은 build_messages()에서 별도 주입."""

    template: str = "너는 {persona_name}다.\n\n{focused_user_context}"

    def render(
        self,
        *,
        persona_name: str | None = None,
        focused_user_context: str | None = None,
        retrieved_memories: str | None = None,  # v2에서는 사용 안 함, 인터페이스 호환용
    ) -> str:
        return self.template.format(
            persona_name=persona_name if persona_name is not None else self.persona_name,
            focused_user_context=(
                focused_user_context
                if focused_user_context is not None
                else self.focused_user_context
            ),
        ).strip()
