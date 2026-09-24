"""PersonaChatService.stream_chat() — 실시간 토큰 스트리밍 async 경로."""

from __future__ import annotations

import asyncio

import pytest

import javstory.llm.llamacpp_backend as backend
from javstory.persona.persona_chat import PersonaChatService


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, lines):
        self._resp = _FakeStreamResponse(lines)

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _FakeAsyncClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kw):
        return _FakeStreamCtx(_FakeAsyncClient.lines)


class _FailingAsyncClient(_FakeAsyncClient):
    def stream(self, method, url, **kw):
        raise RuntimeError("boom")


class _FakeHttpResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FlakyStreamResponse:
    """503(슬롯 준비 안 됨) 응답을 흉내 — raise_for_status()에서 실패시킨다."""

    def raise_for_status(self):
        import httpx

        raise httpx.HTTPStatusError(
            "503", request=None, response=_FakeHttpResponse(503)
        )

    async def aiter_lines(self):
        return
        yield  # pragma: no cover - never reached, makes this an async generator


class _FlakyStreamCtx:
    def __init__(self, fail: bool, lines):
        self._fail = fail
        self._lines = lines

    async def __aenter__(self):
        return _FlakyStreamResponse() if self._fail else _FakeStreamResponse(self._lines)

    async def __aexit__(self, *exc):
        return False


class _ServiceUnavailableThenSuccessClient(_FakeAsyncClient):
    """처음 두 번은 503, 세 번째는 성공 — llama-server가 막 기동/교체돼 슬롯이
    아직 안 열린 찰나의 창을 흉내낸다."""

    call_count = 0
    lines: list[str] = []

    def stream(self, method, url, **kw):
        type(self).call_count += 1
        fail = type(self).call_count < 3
        return _FlakyStreamCtx(fail, type(self).lines)


def _make_service(monkeypatch) -> PersonaChatService:
    service = PersonaChatService()
    monkeypatch.setattr(service, "_resolve_backend", lambda: ("http://fake/v1", "test-model", ""))
    monkeypatch.setattr(
        service,
        "_build_payload",
        lambda **kw: {"model": kw["model"], "messages": [], "temperature": 0.7, "max_tokens": 200, "stream": False},
    )
    monkeypatch.setattr(service.enhanced_memory_store, "record_turn", lambda *a, **kw: None)
    monkeypatch.setattr(service.enhanced_memory_store, "save_to_json", lambda *a, **kw: None)
    monkeypatch.setattr("javstory.persona.persona_chat.persona_chat_uses_managed_llamacpp", lambda: False)
    return service


async def _collect(service: PersonaChatService, message: str) -> list[dict]:
    events = []
    async for event in service.stream_chat(message, history=[]):
        events.append(event)
    return events


def test_stream_chat_yields_tokens_then_done(monkeypatch):
    service = _make_service(monkeypatch)
    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"content":"안녕"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"하세요"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FakeAsyncClient)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]
    assert [e["text"] for e in token_events] == ["안녕", "하세요"]
    assert len(done_events) == 1
    assert "안녕" in done_events[0]["text"]
    assert backend.get_active_llamacpp_requests() == 0


def test_stream_chat_emits_reasoning_events_separately(monkeypatch):
    service = _make_service(monkeypatch)
    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"곰곰이 "},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"reasoning_content":"생각해보면"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"안녕하세요"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FakeAsyncClient)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert [e["text"] for e in reasoning_events] == ["곰곰이 ", "생각해보면"]


def test_stream_chat_does_not_leak_plain_reasoning_into_answer(monkeypatch):
    """--reasoning-format deepseek로 서버가 reasoning_content를 이미 깔끔히 분리해
    주면, <think> 태그도 "최종:" 마커도 없는 순수 사고 과정 문장이 그대로
    _strip_reasoning_leak를 통과해 답변으로 노출되면 안 된다(회귀: "Here's a
    thinking..."이 그대로 답변으로 나오던 버그)."""
    service = _make_service(monkeypatch)
    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"Here is a thinking about how to answer this."},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"실제 답변입니다."},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FakeAsyncClient)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]
    # content 델타로만 "token" 이벤트가 와야 한다 — reasoning이 섞여 들어가면 안 됨.
    assert [e["text"] for e in token_events] == ["실제 답변입니다."]
    assert "Here" not in done_events[0]["text"]
    assert "실제 답변입니다" in done_events[0]["text"]


def test_stream_chat_falls_back_to_reasoning_when_content_never_arrives(monkeypatch):
    """content 델타가 끝내 하나도 안 왔으면(구형 설정에서 답이 reasoning_content로만
    몰리는 경우) 그때는 reasoning을 최후의 폴백으로 답변에 써야 한다."""
    service = _make_service(monkeypatch)
    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"이게 사실상 유일한 응답입니다."},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FakeAsyncClient)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    done_events = [e for e in events if e["type"] == "done"]
    assert "이게 사실상 유일한 응답입니다" in done_events[0]["text"]


def test_stream_chat_reports_token_usage_from_final_chunk(monkeypatch):
    service = _make_service(monkeypatch)
    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"content":"안녕"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"하세요"},"finish_reason":"stop"}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":34,"total_tokens":46}}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FakeAsyncClient)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    done = [e for e in events if e["type"] == "done"][0]
    assert done["usage"] == {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46}
    assert done["tokens_per_sec"] is not None
    assert done["elapsed_sec"] > 0


def test_stream_chat_balances_active_requests_on_error(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _FailingAsyncClient)

    def _boom(*a, **kw):
        raise RuntimeError("no degraded fallback in this test")

    monkeypatch.setattr(service, "_degraded_chat_response", _boom)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    assert any(e["type"] == "error" for e in events)
    assert backend.get_active_llamacpp_requests() == 0


def test_stream_chat_retries_on_503_before_any_token_streamed(monkeypatch):
    """llama-server가 막 기동/교체돼 슬롯이 아직 안 열린 찰나에 503이 나면(로그로
    실제 확인된 회귀) 사용자에게 아무것도 안 보여준 상태이므로 조용히 재시도하고,
    성공하면 정상적으로 토큰이 흘러야 한다 — degraded 폴백으로 떨어지면 안 된다."""
    service = _make_service(monkeypatch)
    _ServiceUnavailableThenSuccessClient.call_count = 0
    _ServiceUnavailableThenSuccessClient.lines = [
        'data: {"choices":[{"delta":{"content":"안녕하세요"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(
        "javstory.persona.persona_chat.httpx.AsyncClient", _ServiceUnavailableThenSuccessClient
    )

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("javstory.persona.persona_chat.asyncio.sleep", _no_sleep)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    assert _ServiceUnavailableThenSuccessClient.call_count == 3
    assert not any(e["type"] == "error" for e in events)
    done_events = [e for e in events if e["type"] == "done"]
    assert "안녕하세요" in done_events[0]["text"]


def test_stream_chat_gives_up_after_max_503_retries(monkeypatch):
    """계속 503이면(예전엔 3회에서 포기 — 실제 로그에서 부족했던 걸로 확인됨) 지금
    설정된 최대 재시도 횟수까지는 계속 시도하고, 그래도 안 되면 그때는 포기한다."""
    from javstory.persona import persona_chat as pc

    service = _make_service(monkeypatch)

    class _AlwaysUnavailableClient(_FakeAsyncClient):
        call_count = 0

        def stream(self, method, url, **kw):
            type(self).call_count += 1
            return _FlakyStreamCtx(True, [])

    _AlwaysUnavailableClient.call_count = 0
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _AlwaysUnavailableClient)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("javstory.persona.persona_chat.asyncio.sleep", _no_sleep)

    def _boom(*a, **kw):
        raise RuntimeError("no degraded fallback in this test")

    monkeypatch.setattr(service, "_degraded_chat_response", _boom)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    assert _AlwaysUnavailableClient.call_count == pc._LLAMACPP_503_MAX_ATTEMPTS
    assert any(e["type"] == "error" for e in events)
    assert backend.get_active_llamacpp_requests() == 0
    assert backend.get_active_llamacpp_requests() == 0


def test_stream_chat_does_not_retry_503_after_tokens_already_streamed(monkeypatch):
    """이미 사용자에게 토큰을 보여준 뒤라면(중간에 슬롯이 끊긴 것) 재시도로 답변을
    처음부터 다시 만들면 중복/혼란스러운 출력이 되므로, 그냥 실패로 처리한다."""
    service = _make_service(monkeypatch)

    class _MidStreamFailure(_FakeAsyncClient):
        def stream(self, method, url, **kw):
            return _MidStreamCtx()

    class _MidStreamResponse:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"일부"},"finish_reason":null}]}'
            import httpx

            raise httpx.HTTPStatusError("503", request=None, response=_FakeHttpResponse(503))

    class _MidStreamCtx:
        async def __aenter__(self):
            return _MidStreamResponse()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _MidStreamFailure)

    def _boom(*a, **kw):
        raise RuntimeError("no degraded fallback in this test")

    monkeypatch.setattr(service, "_degraded_chat_response", _boom)

    backend._active_requests = 0
    events = asyncio.run(_collect(service, "테스트 메시지"))

    assert any(e["type"] == "error" for e in events)
    assert backend.get_active_llamacpp_requests() == 0


def test_estimate_and_clamp_max_tokens_to_ctx():
    """추천 프롬프트처럼 messages 자체가 큰 경우, (프롬프트 추정치 + max_tokens)가
    -c로 띄운 n_ctx_slot(기본 8192)을 넘지 않도록 max_tokens를 깎아야 한다 —
    실제로 겪은 버그: max_tokens=6000 고정이라 프롬프트 2496토큰짜리 추천
    요청에서 llama-server가 8192에서 답변을 강제 절단(truncated=1)했다."""
    from javstory.persona import persona_chat as pc

    big_messages = [
        {"role": "system", "content": "가" * 1800},
        {"role": "user", "content": "나" * 1800},
    ]
    est = pc._estimate_prompt_tokens(big_messages)
    assert est == int(3600 / 1.8)

    big_payload = {"messages": big_messages, "max_tokens": 6000}
    pc._clamp_max_tokens_to_ctx(big_payload)
    assert big_payload["max_tokens"] == 8192 - est - 256
    assert est + big_payload["max_tokens"] + 256 <= 8192

    small_payload = {"messages": [{"role": "user", "content": "안녕"}], "max_tokens": 300}
    pc._clamp_max_tokens_to_ctx(small_payload)
    assert small_payload["max_tokens"] == 300


def test_stream_chat_clamps_max_tokens_when_prompt_is_large(monkeypatch):
    """stream_chat이 실제로 httpx에 보내는 payload의 max_tokens가, 큰 프롬프트일 때
    클램프되는지 종단으로 검증 (위 단위 테스트가 순수 함수 동작을, 이 테스트가
    실제 호출 경로 배선을 검증)."""
    from javstory.persona import persona_chat as pc

    service = _make_service(monkeypatch)
    big_content = "가" * 5000

    monkeypatch.setattr(
        service,
        "_build_payload",
        lambda **kw: {
            "model": kw["model"],
            "messages": [{"role": "user", "content": big_content}],
            "temperature": 0.7,
            "max_tokens": kw["max_tokens"],
            "stream": False,
        },
    )

    sent_payloads: list[dict] = []

    class _CapturingClient(_FakeAsyncClient):
        def stream(self, method, url, **kw):
            sent_payloads.append(kw.get("json"))
            return _FakeStreamCtx(_FakeAsyncClient.lines)

    _FakeAsyncClient.lines = [
        'data: {"choices":[{"delta":{"content":"괜찮아요"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr("javstory.persona.persona_chat.httpx.AsyncClient", _CapturingClient)

    backend._active_requests = 0
    asyncio.run(_collect(service, "오늘 볼만한 작품 추천해 줘"))

    assert sent_payloads, "요청이 실제로 전송되지 않음"
    sent = sent_payloads[0]
    prompt_est = pc._estimate_prompt_tokens(sent["messages"])
    assert sent["max_tokens"] < 6000
    assert prompt_est + sent["max_tokens"] + 256 <= 8192
