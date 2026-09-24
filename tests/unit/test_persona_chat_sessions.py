"""javstory/persona/chat_sessions.py — Persona Chat 대화 이력(세션) 저장소."""

from __future__ import annotations

from javstory.persona import chat_sessions


def test_create_and_list_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    s1 = chat_sessions.create_session()
    s2 = chat_sessions.create_session()
    assert s1["title"] == "새 대화"
    ids = {s["id"] for s in chat_sessions.list_sessions()}
    assert ids == {s1["id"], s2["id"]}


def test_append_turn_auto_titles_from_first_message(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    session = chat_sessions.create_session()
    updated = chat_sessions.append_turn(
        session["id"], "거유 배우 위주로 추천해줘", "네, 이런 작품들이 어울려요.", reasoning="생각중"
    )
    assert updated["title"] == "거유 배우 위주로 추천해줘"
    assert len(updated["messages"]) == 2
    assert updated["messages"][0] == {
        "role": "user",
        "content": "거유 배우 위주로 추천해줘",
        "ts": updated["messages"][0]["ts"],
    }
    assert updated["messages"][1]["role"] == "assistant"
    assert updated["messages"][1]["content"] == "네, 이런 작품들이 어울려요."
    assert updated["messages"][1]["reasoning"] == "생각중"


def test_append_turn_does_not_retitle_after_first_message(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    session = chat_sessions.create_session()
    chat_sessions.append_turn(session["id"], "첫 메시지", "답1")
    updated = chat_sessions.append_turn(session["id"], "두번째 메시지", "답2")
    assert updated["title"] == "첫 메시지"
    assert len(updated["messages"]) == 4


def test_append_turn_creates_session_if_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    import uuid

    sid = uuid.uuid4().hex
    updated = chat_sessions.append_turn(sid, "안녕", "안녕하세요")
    assert updated["id"] == sid
    assert chat_sessions.get_session(sid) is not None


def test_rename_and_delete_session(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    session = chat_sessions.create_session()
    renamed = chat_sessions.rename_session(session["id"], "  내 대화  ")
    assert renamed["title"] == "내 대화"
    assert chat_sessions.delete_session(session["id"]) is True
    assert chat_sessions.get_session(session["id"]) is None
    assert chat_sessions.delete_session(session["id"]) is False


def test_rename_unknown_session_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    assert chat_sessions.rename_session("nonexistent", "x") is None


def test_list_sessions_ignores_non_uuid_files(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_sessions, "SESSIONS_DIR", tmp_path)
    (tmp_path / "not-a-session-id.json").write_text("{}", encoding="utf-8")
    chat_sessions.create_session()
    assert len(chat_sessions.list_sessions()) == 1
