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


def test_persona_chat_memory_records_best_reaction_from_assistant_code(tmp_path, monkeypatch):
    from javstory.persona.persona_memory import PersonaChatMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = PersonaChatMemory(path=tmp_path / "persona_chat_memory.json", max_notes=3)

    memory.record_turn(
        "이거 최고야. 완전 좋다.",
        "방금 말한 HBAD-509의 긴장감에 반응한 거야.",
    )

    notes = memory.prompt_context("추천", max_items=3)["strong_reaction_notes"]
    assert notes
    assert notes[-1]["product_codes"] == ["HBAD-509"]
    assert "최고" in notes[-1]["triggers"]
    assert notes[-1]["intensity"] >= 7


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


# ── 통합 메모리 (EnhancedPersonaMemory.record_turn / prompt_context) ─────────

def test_enhanced_memory_record_turn_strong_reaction(monkeypatch):
    """record_turn()이 강렬 반응을 strong_reaction_notes 에 기록한다."""
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = EnhancedPersonaMemory()
    memory.record_turn(
        "HBAD-509 이거 미쳤어. 완전 개꼴 포인트야.",
        "그 작품의 관계성과 긴장감에 강하게 반응한 거야.",
    )

    assert memory.turn_count == 1
    assert memory.working_memory  # add_turn 도 호출됨
    assert memory.strong_reaction_notes
    assert memory.strong_reaction_notes[-1]["product_codes"] == ["HBAD-509"]
    assert "개꼴" in memory.strong_reaction_notes[-1]["triggers"]

    ctx = memory.prompt_context("HBAD-509", max_items=2)
    assert ctx["strong_reaction_notes"][0]["product_codes"] == ["HBAD-509"]
    assert ctx["turn_count"] == 1


def test_enhanced_memory_record_turn_negative_feedback(monkeypatch):
    """record_turn()이 부정 피드백을 negative_feedback_notes 에 기록한다."""
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = EnhancedPersonaMemory()
    memory.record_turn(
        "ABP-123 이건 별로야. 내 취향 아님.",
        "알겠어. 다음에는 피해서 볼게.",
    )

    assert memory.negative_feedback_notes
    assert memory.negative_feedback_notes[-1]["product_codes"] == ["ABP-123"]
    assert "별로" in memory.negative_feedback_notes[-1]["triggers"]

    ctx = memory.prompt_context("추천해줘", max_items=2)
    assert ctx["negative_feedback_notes"]


def test_enhanced_memory_save_load_roundtrip_with_notes(tmp_path, monkeypatch):
    """save_to_json/load_from_json 왕복이 note 필드를 보존한다."""
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    path = tmp_path / "unified_memory.json"
    memory = EnhancedPersonaMemory()
    memory.record_turn(
        "HBAD-509 진짜 미쳤다.",
        "강렬한 반응이네.",
    )
    memory.save_to_json(str(path))

    loaded = EnhancedPersonaMemory()
    loaded.load_from_json(str(path))

    assert loaded.turn_count == 1
    assert loaded.working_memory
    assert loaded.strong_reaction_notes
    assert loaded.strong_reaction_notes[-1]["product_codes"] == ["HBAD-509"]
    assert loaded.product_mentions.get("HBAD-509")


def test_enhanced_memory_load_recent_messages(monkeypatch):
    """load_recent_messages()가 working_memory를 messages 형식으로 반환한다."""
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1")
    memory = EnhancedPersonaMemory()
    memory.record_turn("마사지 추천해줘", "좋아.\n\n1. **ABC-123** 추천할게.")

    messages = memory.load_recent_messages()
    assert any(m["role"] == "user" and "마사지" in m["content"] for m in messages)
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert "\n\n1. **ABC-123**" in assistant["content"]
