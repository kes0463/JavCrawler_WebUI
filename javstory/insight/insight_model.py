"""Insight chat workers."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import httpx
from PySide6.QtCore import QThread, Signal

from javstory.llm.llamacpp_backend import llamacpp_request_scope
from javstory.persona.persona_chat import (
    ENHANCED_PERSONA_MEMORY_PATH,
    PersonaChatService,
    _situational_max_tokens,
    _situational_temperature,
    _strip_reasoning_leak,
)


_SENTENCE_ENDINGS = {".", "!", "?", "\n", "。", "！", "？"}


class StreamingChatWorker(QThread):
    """Stream Persona Chat responses from an OpenAI-compatible backend."""

    token_received = Signal(str)
    response_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        user_message: str,
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
        product_code: str | None = None,
        service: PersonaChatService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.user_message = str(user_message or "").strip()
        self.history = list(history or [])
        self.product_code = product_code
        self.service = service or PersonaChatService()

    def run(self) -> None:
        """Stream tokens, emit sentence-sized chunks, and finish safely."""
        try:
            if not self.user_message:
                self.response_completed.emit("")
                return

            base_url, model, api_key = self.service._resolve_backend()
            req_temperature = _situational_temperature(self.user_message, self.service.temperature)
            req_max_tokens = _situational_max_tokens(self.user_message, self.service.max_tokens)
            payload = self.service._build_payload(
                model=model,
                text=self.user_message,
                history=self.history,
                product_code=self.product_code,
                temperature=req_temperature,
                max_tokens=req_max_tokens,
            )
            payload["stream"] = True
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

            full_text = ""
            sentence_buffer = ""
            with httpx.Client(timeout=httpx.Timeout(self.service.timeout_sec, connect=5.0)) as client:
                with llamacpp_request_scope():
                    with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            chunk = self._parse_stream_line(line)
                            if not chunk:
                                continue
                            full_text += chunk
                            sentence_buffer += chunk
                            if self._should_emit(sentence_buffer):
                                self.token_received.emit(sentence_buffer)
                                sentence_buffer = ""

            full_text = _strip_reasoning_leak(full_text)
            if sentence_buffer and full_text:
                self.token_received.emit(sentence_buffer)
            if full_text:
                self._record_memory(full_text)
            self.response_completed.emit(full_text)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def _record_memory(self, content: str) -> None:
        try:
            self.service.memory_store.record_turn(self.user_message, content)
        except Exception:
            pass
        try:
            self.service.enhanced_memory_store.add_turn(self.user_message, content)
            self.service.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
        except Exception:
            pass

    @staticmethod
    def _should_emit(buffer: str) -> bool:
        text = str(buffer or "")
        if not text:
            return False
        if text[-1] in _SENTENCE_ENDINGS:
            return True
        stripped = text.rstrip()
        return bool(stripped and stripped[-1] in _SENTENCE_ENDINGS)

    @staticmethod
    def _parse_stream_line(line: str) -> str:
        raw = str(line or "").strip()
        if not raw:
            return ""
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if raw == "[DONE]":
            return ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        try:
            delta = (payload.get("choices") or [{}])[0].get("delta") or {}
        except Exception:
            delta = {}
        content = delta.get("content")
        return content if isinstance(content, str) else ""


__all__ = ["StreamingChatWorker"]
