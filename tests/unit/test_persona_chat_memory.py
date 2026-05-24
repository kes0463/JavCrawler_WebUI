from __future__ import annotations


def test_persona_chat_memory_records_strong_reaction(tmp_path, monkeypatch):
    from javstory.persona.persona_memory import PersonaChatMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = PersonaChatMemory(path=tmp_path / "persona_chat_memory.json", max_notes=3)

    memory.record_turn(
        "HBAD-509 이거 미쳤어. 완전 개꼴 포인트야.",
        "그 작품의 관계성과 긴장감에 강하게 반응한 거야.",
    )

    payload = memory.load()
    notes = payload["strong_reaction_notes"]
    assert notes
    assert notes[-1]["product_codes"] == ["HBAD-509"]
    assert "개꼴" in notes[-1]["triggers"]

    context = memory.prompt_context("HBAD-509", max_items=2)
    assert context["strong_reaction_notes"][0]["product_codes"] == ["HBAD-509"]


def test_persona_chat_memory_records_negative_feedback(tmp_path, monkeypatch):
    from javstory.persona.persona_memory import PersonaChatMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = PersonaChatMemory(path=tmp_path / "persona_chat_memory.json", max_notes=3)

    memory.record_turn(
        "ABP-123 이건 별로야. 내 취향 아님.",
        "알겠어. 다음 추천에서는 그 결을 피해서 볼게.",
    )

    context = memory.prompt_context("추천해줘", max_items=2)
    notes = context["negative_feedback_notes"]
    assert notes
    assert notes[-1]["product_codes"] == ["ABP-123"]
    assert "별로" in notes[-1]["triggers"]
