from __future__ import annotations


def test_streaming_chat_worker_parses_openai_sse_line():
    from javstory.insight.insight_model import StreamingChatWorker

    line = 'data: {"choices":[{"delta":{"content":"안녕."}}]}'

    assert StreamingChatWorker._parse_stream_line(line) == "안녕."
    assert StreamingChatWorker._parse_stream_line("data: [DONE]") == ""
    assert StreamingChatWorker._parse_stream_line("") == ""


def test_streaming_chat_worker_sentence_boundary():
    from javstory.insight.insight_model import StreamingChatWorker

    assert StreamingChatWorker._should_emit("아직 진행 중") is False
    assert StreamingChatWorker._should_emit("문장 끝.") is True
    assert StreamingChatWorker._should_emit("줄 끝\n") is True


def test_streaming_chat_worker_formats_final_response(monkeypatch):
    from javstory.insight.insight_model import StreamingChatWorker

    emitted: list[str] = []
    worker = StreamingChatWorker("테스트", service=object())
    worker._record_memory = lambda _content: None
    worker.response_completed.connect(emitted.append)

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"(낮게 속삭이며) 좋아요. "}}]}'
            yield 'data: {"choices":[{"delta":{"content":"1. **ABC-123 (테스트)**: 설명입니다."}}]}'

    class DummyClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def close(self):
            return None

        def stream(self, *_args, **_kwargs):
            return DummyResponse()

    class DummyService:
        temperature = 0.78
        max_tokens = 1200
        timeout_sec = 1

        def _resolve_backend(self):
            return "http://test/v1", "model", "key"

        def _build_payload(self, **_kwargs):
            return {"messages": []}

    monkeypatch.setattr("javstory.insight.insight_model.httpx.Client", DummyClient)
    worker.service = DummyService()

    worker.run()

    assert emitted
    assert "(낮게 속삭이며)\n\n좋아요." in emitted[-1]
    assert "\n\n1. **ABC-123" in emitted[-1]


def test_streaming_chat_worker_marks_length_truncation(monkeypatch):
    from javstory.insight.insight_model import StreamingChatWorker

    emitted: list[str] = []
    worker = StreamingChatWorker("테스트", service=object())
    worker._record_memory = lambda _content: None
    worker.response_completed.connect(emitted.append)

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"긴 답변입니다."}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'

    class DummyClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def close(self):
            return None

        def stream(self, *_args, **_kwargs):
            return DummyResponse()

    class DummyService:
        temperature = 0.78
        max_tokens = 1200
        timeout_sec = 1

        def _resolve_backend(self):
            return "http://test/v1", "model", "key"

        def _build_payload(self, **_kwargs):
            return {"messages": []}

    monkeypatch.setattr("javstory.insight.insight_model.httpx.Client", DummyClient)
    worker.service = DummyService()

    worker.run()

    assert emitted
    assert "이어" in emitted[-1]


def test_streaming_chat_worker_retry_rejects_stage_direction():
    from javstory.insight.insight_model import StreamingChatWorker

    class DummyService:
        def chat(self, *_args, **_kwargs):
            return {"choices": [{"message": {"content": "(깊게 숨을 들이마시며"}}]}

    worker = StreamingChatWorker("테스트", service=DummyService())

    assert worker._retry_non_streaming_final() == ""


def test_streaming_chat_worker_cancel_closes_active_http_handles():
    from javstory.insight.insight_model import StreamingChatWorker

    class DummyHandle:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    client = DummyHandle()
    response = DummyHandle()
    worker = StreamingChatWorker("테스트", service=object())
    worker._set_active_http(client=client, response=response)

    worker.cancel()

    assert worker._cancelled is True
    assert client.closed is True
    assert response.closed is True


def test_insight_model_cancel_persona_chat_updates_running_immediately(monkeypatch):
    import sys

    from PySide6.QtWidgets import QApplication

    from gui.models.insight_model import InsightModel

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    monkeypatch.setattr(InsightModel, "_load_persona_chat_history", staticmethod(lambda: []))
    model = InsightModel()

    class DummyWorker:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    worker = DummyWorker()
    model._persona_chat_worker = worker
    model._persona_chat_running = True
    model._persona_chat_history = [{"role": "user", "content": "테스트", "status": "ok"}]

    model.cancelPersonaChat()

    assert worker.cancelled is True
    assert model.isPersonaChatRunning is False
    assert model._persona_chat_cancel_requested is True
    assert model._persona_chat_history[-1]["status"] == "cancelled"


def test_insight_model_loads_enhanced_persona_chat_history(tmp_path, monkeypatch):
    from gui.models.insight_model import InsightModel
    from javstory.persona import persona_chat as pc
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    path = tmp_path / "persona_chat_enhanced_memory.json"
    memory = EnhancedPersonaMemory()
    memory.record_turn(
        "오늘의 작품 추천",
        "좋아요. 1. **ABC-123**: 첫 추천입니다. 2. **DEF-456**: 둘째 추천입니다.",
    )
    memory.save_to_json(str(path))
    monkeypatch.setattr(pc, "ENHANCED_PERSONA_MEMORY_PATH", path)

    messages = InsightModel._load_persona_chat_history()

    assert messages
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "오늘의 작품 추천"
    assert messages[1]["role"] == "assistant"
    assert "ABC-123" in messages[1]["content"]
    assert "\n\n1. **ABC-123**" in messages[1]["content"]
    assert "\n\n2. **DEF-456**" in messages[1]["content"]
