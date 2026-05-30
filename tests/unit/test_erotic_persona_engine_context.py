from __future__ import annotations


def test_build_chat_context_emphasizes_sensual_priority(monkeypatch):
    from javstory.persona import erotic_persona_engine as engine_mod
    from javstory.persona.erotic_persona_engine import EroticPersonaEngine

    captured = {}

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {
                "strong_reaction_notes": [
                    {"text": "A 반응", "triggers": ["개꼴"], "product_codes": ["AAA-111"], "intensity": 6},
                    {"text": "B 반응", "triggers": ["긴장감"], "product_codes": ["BBB-222"], "intensity": 8},
                    {"text": "C 반응", "triggers": ["마사지"], "product_codes": ["CCC-333"], "intensity": 7},
                    {"text": "D 반응", "triggers": ["배우"], "product_codes": ["DDD-444"], "intensity": 9},
                ]
            }

    monkeypatch.setattr(engine_mod, "EnhancedPersonaMemory", lambda: DummyMemory())
    monkeypatch.setattr(
        engine_mod.HybridLibrarySearch,
        "search_with_fusion",
        lambda self, query: captured.setdefault("query", query) and [],
    )

    engine = EroticPersonaEngine()
    monkeypatch.setattr(
        engine,
        "persona_snapshot",
        lambda: {
            "persona_type": "테스트형",
            "summary": "일반 요약",
            "sensual_summary": "마사지 긴장감에 약한 취향",
            "turn_ons": ["마사지", "긴장감"],
            "avoidances": ["코미디"],
            "affinities": [],
            "evidence": [],
            "source": "test",
        },
    )

    ctx = engine.build_chat_context("마사지 추천")
    priority = ctx["sensual_priority_context"]

    assert priority["priority"] == "highest"
    assert priority["sensual_summary"] == "마사지 긴장감에 약한 취향"
    assert "가장 중요하게 고려" in priority["instruction"]
    assert len(priority["strong_reactions_top3"]) == 3
    assert priority["strong_reactions_top3"][0]["product_codes"] == ["DDD-444"]
    assert "마사지" in priority["trigger_summary"]
    assert priority["turn_ons_emphasis"]["items"] == ["마사지", "긴장감"]
    assert priority["avoidances_emphasis"]["items"] == ["코미디"]
    guide = priority["recommendation_reasoning_guide"]
    assert guide["must_explain"]
    assert "sensual_summary" in guide["must_explain"][1]
    assert "크게 자극받을 가능성" in guide["must_explain"][3]
    assert "최근 강한 반응 작품과 자극 축" in captured["query"]
    assert ctx["library_search"]["fallback_seed_codes"] == ["DDD-444", "BBB-222", "CCC-333"]


def test_build_chat_context_selects_persona_fields_by_intent(monkeypatch):
    from javstory.persona import erotic_persona_engine as engine_mod
    from javstory.persona.erotic_persona_engine import EroticPersonaEngine

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {"strong_reaction_notes": []}

    monkeypatch.setattr(engine_mod, "EnhancedPersonaMemory", lambda: DummyMemory())
    monkeypatch.setattr(engine_mod.HybridLibrarySearch, "search_with_fusion", lambda self, query: [])

    engine = EroticPersonaEngine()
    monkeypatch.setattr(
        engine,
        "persona_snapshot",
        lambda: {
            "persona_type": "테스트형",
            "summary": "전체 요약",
            "sensual_summary": "관능 요약",
            "turn_ons": ["긴장감"],
            "avoidances": ["코미디"],
            "affinities": ["몰입"],
            "evidence": [{"product_code": "AAA-111", "reason": "근거"}],
            "source": "test",
        },
    )

    rec_ctx = engine.build_chat_context("긴장감 있는 작품 추천해줘")
    rec_persona = rec_ctx["persona"]
    assert rec_persona["intent"] == "recommendation"
    assert "turn_ons" in rec_persona["included_fields"]
    assert "evidence" not in rec_persona

    analysis_ctx = engine.build_chat_context("내 취향 분석해줘")
    analysis_persona = analysis_ctx["persona"]
    assert analysis_persona["intent"] == "self_analysis"
    assert "summary" in analysis_persona["included_fields"]
    assert "evidence" in analysis_persona


def test_product_snapshot_rejects_mismatched_grok_product_code(monkeypatch):
    from javstory.persona import erotic_persona_engine as engine_mod
    from javstory.persona.erotic_persona_engine import EroticPersonaEngine

    class DummyQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return None

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def query(self, *_args, **_kwargs):
            return DummyQuery()

    monkeypatch.setattr(engine_mod, "get_db_session_ctx", lambda: DummySession())
    monkeypatch.setattr(
        "javstory.translation.story_grok_module.load_cached_grok_json_flexible",
        lambda _code: {
            "product_code": "WRONG-999",
            "verification_ok": True,
            "code_mismatch": False,
            "overall_summary": "다른 작품 요약",
            "scenes": [],
        },
    )

    data = EroticPersonaEngine().product_snapshot("ABC-123")

    assert "story_context" not in data
    assert data["story_context_status"]["reason"] == "grok_product_code_mismatch"
    assert data["story_context_status"]["grok_product_code"] == "WRONG-999"
