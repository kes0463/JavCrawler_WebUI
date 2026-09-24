"""webapi persona-chat 라우트 테스트."""

from __future__ import annotations

import pytest


@pytest.fixture
def persona_chat_client(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from webapi.main import app
    from javstory.persona import chat_sessions

    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path / "persona_chat_sessions")

    return TestClient(app)


def test_sse_gen_stops_generation_on_client_disconnect(monkeypatch):
    """'중지' 버튼 = 클라이언트가 fetch를 abort → is_disconnected()가 True가 되면
    남은 스트림을 이어가지 않고 stream_chat()의 async generator를 aclose()해야 한다."""
    import asyncio

    from webapi.routes import persona_chat as persona_chat_mod

    closed: list[bool] = []

    async def fake_stream_chat(message, *, history=None, product_code=None):
        try:
            yield {"type": "token", "text": "안"}
            yield {"type": "token", "text": "녕"}
            yield {"type": "done", "text": "안녕"}
        except GeneratorExit:
            closed.append(True)
            raise

    monkeypatch.setattr(persona_chat_mod._service, "stream_chat", fake_stream_chat)

    class FakeRequest:
        def __init__(self):
            self._calls = 0

        async def is_disconnected(self):
            self._calls += 1
            return self._calls >= 1  # 첫 이벤트 직후부터 연결 끊김으로 취급

    async def _run():
        events = []
        async for frame in persona_chat_mod._sse_gen(FakeRequest(), None, "안녕", [], None):
            events.append(frame)
        return events

    events = asyncio.run(_run())
    assert len(events) == 1  # 첫 토큰만 내보내고 중단
    assert "안" in events[0]
    assert closed == [True]


def test_sse_gen_persists_turn_to_session_on_completion(monkeypatch):
    import asyncio

    from javstory.persona import chat_sessions
    from webapi.routes import persona_chat as persona_chat_mod

    async def fake_stream_chat(message, *, history=None, product_code=None):
        yield {"type": "token", "text": "안녕"}
        yield {"type": "reasoning", "text": "생각해보니"}
        yield {"type": "done", "text": "안녕하세요"}

    monkeypatch.setattr(persona_chat_mod._service, "stream_chat", fake_stream_chat)

    saved: list[tuple] = []
    monkeypatch.setattr(
        chat_sessions,
        "append_turn",
        lambda sid, u, a, *, reasoning="": saved.append((sid, u, a, reasoning)),
    )

    class FakeRequest:
        async def is_disconnected(self):
            return False

    async def _run():
        async for _ in persona_chat_mod._sse_gen(FakeRequest(), "sess-1", "안녕", [], None):
            pass

    asyncio.run(_run())
    assert saved == [("sess-1", "안녕", "안녕하세요", "생각해보니")]


def test_persona_chat_session_crud(persona_chat_client):
    res = persona_chat_client.post("/api/persona-chat/sessions")
    assert res.status_code == 200
    session = res.json()
    assert session["title"] == "새 대화"
    session_id = session["id"]

    res = persona_chat_client.get("/api/persona-chat/sessions")
    assert res.status_code == 200
    assert any(s["id"] == session_id for s in res.json()["sessions"])

    res = persona_chat_client.get(f"/api/persona-chat/sessions/{session_id}")
    assert res.status_code == 200
    assert res.json()["messages"] == []

    res = persona_chat_client.patch(
        f"/api/persona-chat/sessions/{session_id}", json={"title": "취향 상담"}
    )
    assert res.status_code == 200
    assert res.json()["title"] == "취향 상담"

    res = persona_chat_client.delete(f"/api/persona-chat/sessions/{session_id}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True}

    res = persona_chat_client.get(f"/api/persona-chat/sessions/{session_id}")
    assert res.status_code == 404


def test_persona_chat_get_unknown_session_404(persona_chat_client):
    res = persona_chat_client.get("/api/persona-chat/sessions/does-not-exist")
    assert res.status_code == 404
