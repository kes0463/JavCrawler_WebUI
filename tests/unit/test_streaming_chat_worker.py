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


def test_streaming_chat_worker_retry_rejects_stage_direction():
    from javstory.insight.insight_model import StreamingChatWorker

    class DummyService:
        def chat(self, *_args, **_kwargs):
            return {"choices": [{"message": {"content": "(깊게 숨을 들이마시며"}}]}

    worker = StreamingChatWorker("테스트", service=DummyService())

    assert worker._retry_non_streaming_final() == ""
