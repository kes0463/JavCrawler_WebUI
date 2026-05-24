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


def test_enhanced_persona_memory_working_memory_limit():
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    memory = EnhancedPersonaMemory()
    for idx in range(13):
        memory.add_turn(f"user {idx}", f"assistant {idx}")

    assert len(memory.working_memory) == 12
    assert memory.working_memory[0]["user"] == "user 1"


def test_enhanced_persona_memory_save_load_legacy_compatible(tmp_path):
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    path = tmp_path / "enhanced_memory.json"
    memory = EnhancedPersonaMemory()
    memory.add_turn("마사지 취향이 좋아", "그 취향을 기억할게")
    memory.semantic_memory["마사지"] = 2.0
    memory.save_to_json(str(path))

    loaded = EnhancedPersonaMemory()
    loaded.load_from_json(str(path))

    assert loaded.working_memory
    assert loaded.semantic_memory["마사지"] == 2.0

    legacy_path = tmp_path / "legacy_memory.json"
    legacy_path.write_text(
        """
{
  "recent_messages": [
    {"role": "user", "content": "HBAD-509 좋아"},
    {"role": "assistant", "content": "그 취향을 기억할게"}
  ],
  "preference_notes": [{"text": "마사지 취향", "weight": 3}]
}
""",
        encoding="utf-8",
    )
    legacy_loaded = EnhancedPersonaMemory()
    legacy_loaded.load_from_json(str(legacy_path))

    assert legacy_loaded.working_memory[0]["user"] == "HBAD-509 좋아"
    assert legacy_loaded.semantic_memory["마사지 취향"] == 3.0


def test_enhanced_persona_memory_retrieve_relevant_context():
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    memory = EnhancedPersonaMemory()
    memory.episodic_memory = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "summary": "마사지 긴장감 관계성 취향",
            "turn_count": 4,
            "new_preferences": ["마사지"],
            "important_context": ["긴장감"],
            "special_requests": [],
        },
        {
            "timestamp": "2026-01-02T00:00:00+00:00",
            "summary": "코미디 밝은 분위기",
            "turn_count": 2,
        },
    ]

    context = memory.retrieve_relevant_context("마사지 긴장감", max_items=1)
    assert "마사지" in context
    assert "similarity" in context
