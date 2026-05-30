"""Insight chat workers."""

from __future__ import annotations

import json
import threading
from typing import Any, Mapping, Sequence

import httpx
from PySide6.QtCore import QThread, Signal

from javstory.llm.llamacpp_backend import llamacpp_request_scope
from javstory.persona.persona_chat import (
    ENHANCED_PERSONA_MEMORY_PATH,
    PersonaChatService,
    _deterministic_recommendation_response,
    _format_chat_response_text,
    _is_incomplete_stage_direction_response,
    _is_qwen_llamacpp_context_limited,
    _persona_chat_max_tokens_for_context,
    _recommendation_candidates_from_payload,
    _recommendation_response_needs_replacement,
    _situational_temperature,
    _strip_reasoning_leak,
    _with_truncation_note,
)


_SENTENCE_ENDINGS = {".", "!", "?", "\n", "。", "！", "？"}


class StreamingChatWorker(QThread):
    """Stream Persona Chat responses from an OpenAI-compatible backend."""

    token_received = Signal(str)
    response_completed = Signal(str)
    error_occurred = Signal(str)
    cancelled = Signal()  # 사용자가 취소 버튼을 눌러 스트리밍을 중단했을 때 emit

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
        self._retried_non_streaming = False
        self._cancelled = False
        self._http_lock = threading.Lock()
        self._active_client: Any | None = None
        self._active_response: Any | None = None

    def cancel(self) -> None:
        """스트리밍 취소를 요청하고, 대기 중인 HTTP 스트림을 즉시 닫는다."""
        self._cancelled = True
        self.requestInterruption()
        self._close_active_http()

    def _set_active_http(
        self,
        *,
        client: Any | None = None,
        response: Any | None = None,
    ) -> None:
        with self._http_lock:
            if client is not None:
                self._active_client = client
            if response is not None:
                self._active_response = response

    def _clear_active_http(self) -> None:
        with self._http_lock:
            self._active_response = None
            self._active_client = None

    def _close_active_http(self) -> None:
        with self._http_lock:
            response = self._active_response
            client = self._active_client
        for handle in (response, client):
            if handle is None:
                continue
            try:
                handle.close()
            except Exception:
                pass

    def run(self) -> None:
        """Stream tokens, emit sentence-sized chunks, and finish safely."""
        try:
            if not self.user_message:
                self.response_completed.emit("")
                return

            base_url, model, api_key = self.service._resolve_backend()
            req_temperature = _situational_temperature(self.user_message, self.service.temperature)
            req_max_tokens = _persona_chat_max_tokens_for_context(self.user_message, self.service.max_tokens)
            payload = self.service._build_payload(
                model=model,
                text=self.user_message,
                history=self.history,
                product_code=self.product_code,
                temperature=req_temperature,
                max_tokens=req_max_tokens,
                compact=_is_qwen_llamacpp_context_limited(),
            )
            payload["stream"] = True
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            candidates, recent_codes = _recommendation_candidates_from_payload(payload)
            if self._cancelled or self.isInterruptionRequested():
                self.cancelled.emit()
                return

            full_text = ""
            sentence_buffer = ""
            finish_reason = "stop"
            try:
                with httpx.Client(timeout=httpx.Timeout(self.service.timeout_sec, connect=5.0)) as client:
                    self._set_active_http(client=client)
                    with llamacpp_request_scope():
                        with client.stream(
                            "POST",
                            f"{base_url}/chat/completions",
                            json=payload,
                            headers=headers,
                        ) as response:
                            self._set_active_http(response=response)
                            response.raise_for_status()
                            for line in response.iter_lines():
                                if self._cancelled or self.isInterruptionRequested():
                                    break
                                event = self._parse_stream_event(line)
                                if event.get("finish_reason"):
                                    finish_reason = str(event.get("finish_reason") or "stop")
                                chunk = str(event.get("content") or "")
                                if not chunk:
                                    continue
                                full_text += chunk
                                sentence_buffer += chunk
                                if self._should_emit(sentence_buffer):
                                    self.token_received.emit(sentence_buffer)
                                    sentence_buffer = ""
            finally:
                self._clear_active_http()

            # 취소된 경우: 메모리 저장 없이 cancelled 시그널만 emit
            if self._cancelled or self.isInterruptionRequested():
                self.cancelled.emit()
                return

            full_text = _strip_reasoning_leak(full_text)
            if full_text and _is_incomplete_stage_direction_response(full_text):
                full_text = self._retry_non_streaming_final()
                sentence_buffer = full_text
            full_text = _format_chat_response_text(full_text)
            full_text = _with_truncation_note(full_text, finish_reason)
            needs_replacement = _recommendation_response_needs_replacement(
                self.user_message,
                full_text,
                candidates,
                recent_codes,
            )
            if needs_replacement:
                full_text = _deterministic_recommendation_response(
                    self.user_message,
                    candidates,
                    recent_codes,
                )
                finish_reason = "stop"
            if full_text and not self._retried_non_streaming:
                self._record_memory(full_text)
            self.response_completed.emit(full_text)
        except Exception as exc:
            status_code = None
            response_tail = ""
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                status_code = exc.response.status_code
                try:
                    response_tail = exc.response.text[-1500:]
                except Exception:
                    response_tail = ""
            if (
                status_code == 400
                and "exceeds the available context size" in response_tail
                and not self._cancelled
            ):
                fallback_text = self._retry_context_limited_final()
                if fallback_text:
                    self.response_completed.emit(fallback_text)
                    return
            if self._cancelled:
                self.cancelled.emit()
            else:
                self.error_occurred.emit(str(exc))

    def _retry_context_limited_final(self) -> str:
        """Fallback for llama.cpp 400 context overflow on the streaming path."""
        try:
            response = self.service.chat(
                self.user_message,
                history=[],
                product_code=self.product_code,
                temperature=0.68,
                max_tokens=600,
            )
            content = ((response.get("choices") or [{}])[0].get("message") or {}).get("content")
            cleaned = _format_chat_response_text(_strip_reasoning_leak(str(content or "")))
            return cleaned
        except Exception:
            return ""

    def _retry_non_streaming_final(self) -> str:
        """Fallback when streaming returns only an incomplete stage direction."""
        try:
            self._retried_non_streaming = True
            response = self.service.chat(
                self.user_message,
                history=[],
                product_code=self.product_code,
                temperature=0.75,
                max_tokens=800,
            )
            content = ((response.get("choices") or [{}])[0].get("message") or {}).get("content")
            cleaned = _strip_reasoning_leak(str(content or ""))
            if _is_incomplete_stage_direction_response(cleaned):
                return ""
            return _format_chat_response_text(cleaned)
        except Exception:
            return ""

    def _record_memory(self, content: str) -> None:
        try:
            self.service.enhanced_memory_store.record_turn(self.user_message, content)
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
        return str(StreamingChatWorker._parse_stream_event(line).get("content") or "")

    @staticmethod
    def _parse_stream_event(line: str) -> dict[str, str]:
        raw = str(line or "").strip()
        if not raw:
            return {}
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if raw == "[DONE]":
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        try:
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
        except Exception:
            choice = {}
            delta = {}
        content = delta.get("content")
        finish_reason = choice.get("finish_reason") if isinstance(choice, Mapping) else None
        event: dict[str, str] = {}
        if isinstance(content, str):
            event["content"] = content
        if finish_reason:
            event["finish_reason"] = str(finish_reason)
        return event


__all__ = ["StreamingChatWorker"]
