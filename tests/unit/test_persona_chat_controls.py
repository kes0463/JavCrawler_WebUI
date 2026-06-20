from __future__ import annotations


def test_persona_chat_dynamic_temperature_and_tokens(monkeypatch):
    from javstory.persona.persona_chat import (
        _GENERAL_TEMPERATURE_MAX,
        _LOW_TEMPERATURE_CAP,
        _RECOMMENDATION_TEMPERATURE_CAP,
        _SENSUAL_TEMPERATURE_DEFAULT,
        _SENSUAL_TEMPERATURE_MAX,
        _persona_chat_max_tokens_for_context,
        _situational_max_tokens,
        _situational_temperature,
    )

    # 일반 대화: base=0.78 이 [0.72, 0.82] 안에 있으므로 그대로 반환
    assert _situational_temperature("오늘은 일반 대화로 말해줘", 0.78) == 0.78
    # base > _GENERAL_TEMPERATURE_MAX → max로 클램핑
    assert _situational_temperature("그냥 잡담하자", 1.0) == _GENERAL_TEMPERATURE_MAX
    # 롤플레이 힌트 → _SENSUAL_TEMPERATURE_DEFAULT
    assert _situational_temperature("롤플레이 톤으로 분석해줘", 0.78) == _SENSUAL_TEMPERATURE_DEFAULT
    # 인텐스 힌트 → _SENSUAL_TEMPERATURE_MAX
    assert _situational_temperature("더 야하게 조교해", 0.78) == _SENSUAL_TEMPERATURE_MAX
    # 검색/사실 정보 힌트 → _LOW_TEMPERATURE_CAP
    assert _situational_temperature("품번 정보 찾아줘", 0.78) == _LOW_TEMPERATURE_CAP
    # 추천 요청은 창작보다 근거 고정을 우선하므로 일반 분석보다 낮게 유지
    assert _situational_temperature("오늘의 작품 추천", 0.78) == _RECOMMENDATION_TEMPERATURE_CAP
    # 분석 힌트 → _GENERAL_TEMPERATURE_MAX
    assert _situational_temperature("왜 이 취향에 끌리는지 분석해줘", 0.78) == _GENERAL_TEMPERATURE_MAX

    assert _situational_max_tokens("짧게 요약해줘", 2000) == 800
    assert _situational_max_tokens("더 세게 자세히 분석해줘", 2000) == 2000
    assert _situational_max_tokens("비슷한 추천 자세히", 2000) == 2000
    assert _situational_max_tokens("비슷한 추천 자세히", 2600) == 2400
    assert _situational_max_tokens("더 세게 자세히 분석해줘", 3072) == 3072
    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_MODEL", "qwen3-14b-uncensored")
    monkeypatch.setenv("JAVSTORY_LLAMACPP_CTX", "4096")
    assert _persona_chat_max_tokens_for_context("더 세게 자세히 분석해줘", 3072) == 3072


def test_persona_chat_filters_reasoning_only_payload():
    from javstory.persona.persona_chat import (
        _coalesce_response_text,
        _format_chat_response_text,
        _is_incomplete_stage_direction_response,
        _strip_reasoning_leak,
    )

    payload = {
        "choices": [
            {
                "message": {
                    "reasoning_content": "Thinking Process: hidden draft",
                    "content": "",
                }
            }
        ]
    }
    assert _coalesce_response_text(payload) == ""

    leaked = "Analysis: hidden notes\nFinal Answer: 이 작품은 긴장감과 관계성 때문에 꽂히는 쪽이야."
    assert _strip_reasoning_leak(leaked) == "이 작품은 긴장감과 관계성 때문에 꽂히는 쪽이야."
    assert _is_incomplete_stage_direction_response("(깊게 숨을 들이마시며") is True
    assert _is_incomplete_stage_direction_response("(낮게 웃으며) 네 취향은 긴장감 쪽에 가까워.") is False

    dense = (
        "(낮게 속삭이며) 좋아요. ✨ 🔥 **추천 2가지** 🔥 ✨ "
        "1. **GIGL-568 (테스트)**: 첫 설명입니다. "
        "2. **JUY-908 (테스트)**: 둘째 설명입니다. 자, 이제 뭘 고를래요?"
    )
    formatted = _format_chat_response_text(dense)
    assert "(낮게 속삭이며)\n\n좋아요." in formatted
    assert "\n\n✨ 🔥 **추천 2가지** 🔥 ✨" in formatted
    assert "\n\n1. **GIGL-568" in formatted
    assert "\n\n2. **JUY-908" in formatted
    assert "\n\n자, 이제 뭘 고를래요?" in formatted


def test_persona_chat_applies_personalized_ranking():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    context = {
        "sensual_recommendation_focus": {
            "summary": "마사지 관계성 긴장감",
            "turn_ons": ["마사지", "긴장감"],
        },
        "persona": {
            "sensual_summary": "마사지 관계성",
            "turn_ons": ["마사지"],
            "affinities": [],
        },
        "library_search": {
            "fallback_seed_codes": ["HBAD-509"],
            "results": [
                {
                    "product_code": "AAA-111",
                    "title_ko": "일반 작품",
                    "genres": ["기타"],
                    "source": "db_text",
                    "score": 0.75,
                },
                {
                    "product_code": "BBB-222",
                    "title_ko": "마사지 긴장감 추천작",
                    "genres": ["마사지"],
                    "source": "embedding",
                    "score": 0.7,
                    "grok": {"summary": "마사지 분위기", "tags": ["마사지"], "tones": ["긴장감"], "scene_count": 2},
                },
            ],
        },
    }
    memory = {
        "strong_reaction_notes": [{"product_codes": ["HBAD-509"]}],
        "negative_feedback_notes": [],
    }

    ranked = _apply_personalized_ranking(context, memory)["library_search"]["results"]
    assert ranked[0]["product_code"] == "BBB-222"
    assert ranked[0]["persona_match_score"] > ranked[1]["persona_match_score"]
    assert ranked[0]["ranking_reasons"]


def test_persona_chat_penalizes_negative_feedback_code():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    context = {
        "persona": {"sensual_summary": "마사지", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "results": [
                {"product_code": "BAD-123", "title_ko": "마사지 작품", "genres": ["마사지"], "source": "db_text", "score": 1.0},
                {"product_code": "OK-456", "title_ko": "마사지 추천작", "genres": ["마사지"], "source": "db_text", "score": 0.9},
            ],
        },
    }
    memory = {
        "strong_reaction_notes": [],
        "negative_feedback_notes": [{"product_codes": ["BAD-123"]}],
    }

    ranked = _apply_personalized_ranking(context, memory)["library_search"]["results"]
    assert ranked[0]["product_code"] == "OK-456"
    assert "사용자 부정 피드백 품번이라 감점" in ranked[1]["ranking_reasons"]


def test_persona_chat_ranking_uses_user_watch_signals():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    context = {
        "persona": {"sensual_summary": "마사지", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "results": [
                {
                    "product_code": "LIKE-001",
                    "title_ko": "마사지 추천작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 0.8,
                    "user_rating": 5,
                    "user_liked": True,
                    "user_is_completed": True,
                    "user_completion_ratio": 1.0,
                },
                {
                    "product_code": "LOW-001",
                    "title_ko": "마사지 저평가작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 0.9,
                    "user_rating": 1,
                    "user_disliked": True,
                },
            ],
        },
    }
    ranked = _apply_personalized_ranking(
        context,
        {"strong_reaction_notes": [], "negative_feedback_notes": []},
    )["library_search"]["results"]

    assert ranked[0]["product_code"] == "LIKE-001"
    assert "사용자 좋아요 이력" in ranked[0]["ranking_reasons"]
    assert "사용자 싫어요/낮은 별점 이력이라 감점" in ranked[1]["ranking_reasons"]


def test_persona_chat_penalizes_recently_recommended_codes():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    context = {
        "persona": {"sensual_summary": "마사지 긴장감", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "query": "마사지 작품 추천",
            "results": [
                {
                    "product_code": "OLD-001",
                    "title_ko": "마사지 긴장감 기존 추천작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 1.0,
                },
                {
                    "product_code": "NEW-001",
                    "title_ko": "마사지 긴장감 새 추천작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 0.75,
                },
            ],
        },
    }
    ranked = _apply_personalized_ranking(
        context,
        {
            "strong_reaction_notes": [],
            "negative_feedback_notes": [],
            "recent_recommended_product_codes": ["OLD-001"],
        },
    )["library_search"]

    assert ranked["results"][0]["product_code"] == "NEW-001"
    assert "OLD-001" in ranked["diversity_policy"]["recent_recommended_product_codes"]
    assert any("다양성 감점" in reason for reason in ranked["results"][1]["ranking_reasons"])


def test_persona_chat_fresh_request_filters_recently_recommended_codes():
    from javstory.persona.persona_chat import _apply_personalized_ranking, _is_fresh_recommendation_request

    context = {
        "persona": {"sensual_summary": "마사지 긴장감", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "query": "추천 안 했던 작품 추천해",
            "results": [
                {
                    "product_code": "OLD-001",
                    "title_ko": "마사지 긴장감 기존 추천작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 1.0,
                },
                {
                    "product_code": "NEW-001",
                    "title_ko": "마사지 긴장감 새 추천작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 0.75,
                },
            ],
        },
    }

    ranked = _apply_personalized_ranking(
        context,
        {
            "strong_reaction_notes": [],
            "negative_feedback_notes": [],
            "recent_recommended_product_codes": ["OLD-001"],
        },
    )["library_search"]

    assert _is_fresh_recommendation_request("추천 안 했던 작품 추천해") is True
    assert [item["product_code"] for item in ranked["results"]] == ["NEW-001"]
    assert ranked["diversity_policy"]["fresh_request"] is True
    assert ranked["diversity_policy"]["strict_exclusion_applied"] is True


def test_persona_chat_unwatched_request_filters_watched_candidates():
    from javstory.persona.persona_chat import _apply_personalized_ranking, _is_unwatched_recommendation_request

    context = {
        "persona": {"sensual_summary": "마사지 긴장감", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "query": "내가 안 본 작품 추천해",
            "results": [
                {
                    "product_code": "WATCH-001",
                    "title_ko": "이미 본 고득점 작품",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 1.0,
                    "user_rating": 5,
                    "user_is_completed": True,
                    "user_completion_ratio": 1.0,
                },
                {
                    "product_code": "NEW-001",
                    "title_ko": "아직 안 본 작품",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 0.75,
                },
            ],
        },
    }

    ranked = _apply_personalized_ranking(
        context,
        {"strong_reaction_notes": [], "negative_feedback_notes": []},
    )["library_search"]

    assert _is_unwatched_recommendation_request("내가 안 본 작품 추천해") is True
    assert [item["product_code"] for item in ranked["results"]] == ["NEW-001"]
    assert "unwatched_request_filter" in ranked["ranking_policy"]["weights"]


def test_persona_chat_recommendation_penalizes_strong_reference_code():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    context = {
        "persona": {"sensual_summary": "마사지 긴장감", "turn_ons": ["마사지"], "affinities": []},
        "library_search": {
            "query": "오늘의 작품 추천",
            "fallback_seed_codes": ["OLD-001"],
            "results": [
                {
                    "product_code": "OLD-001",
                    "title_ko": "마사지 긴장감 기준작",
                    "genres": ["마사지"],
                    "source": "db_text",
                    "score": 1.0,
                },
                {
                    "product_code": "NEW-001",
                    "title_ko": "마사지 긴장감 유사작",
                    "genres": ["마사지"],
                    "source": "embedding",
                    "score": 0.6,
                },
            ],
        },
    }

    ranked = _apply_personalized_ranking(
        context,
        {
            "strong_reaction_notes": [{"product_codes": ["OLD-001"]}],
            "negative_feedback_notes": [],
        },
    )["library_search"]["results"]

    assert ranked[0]["product_code"] == "NEW-001"
    assert any("반복 추천 감점" in reason for reason in ranked[1]["ranking_reasons"])


def test_persona_chat_recommendation_grounding_blocks_fake_candidates():
    from javstory.persona.persona_chat import _recommendation_grounding_block

    long_text = "긴장감 " * 120
    context = {
        "persona": {"sensual_summary": "긴장감 취향", "turn_ons": ["긴장감"]},
        "library_search": {
            "results": [
                {
                    "product_code": "ABC-123",
                    "title_ko": "테스트 추천작",
                    "genres": ["드라마"],
                    "source": "db_text",
                    "ranking_reasons": ["sensual_summary/turn_ons 키워드 매칭"],
                    "synopsis": long_text,
                    "grok": {"summary": long_text, "tags": ["긴장감"], "tones": ["차분함"]},
                },
                {"product_code": "DEF-456", "title_ko": "두 번째 추천작", "source": "db_text"},
                {"product_code": "GHI-789", "title_ko": "세 번째 추천작", "source": "db_text"},
                {
                    "product_code": "JKL-111",
                    "title_ko": "네 번째 추천작",
                    "source": "db_text",
                }
            ]
        },
    }

    block = _recommendation_grounding_block(
        "다른 작품 추천해",
        context,
        {
            "recent_recommended_product_codes": [
                "OLD-001",
                "OLD-002",
                "OLD-003",
                "OLD-004",
                "OLD-005",
                "OLD-006",
                "OLD-007",
            ]
        },
    )

    assert "ABC-123" in block
    assert "GHI-789" in block
    assert "JKL-111" not in block
    assert "후보 목록에 없는 품번" in block
    assert "(신규 코드: ...)" in block
    assert "recent_recommended_product_codes: OLD-001" in block
    assert "OLD-007" in block
    assert "grok.tags" not in block
    assert "grok.tones" not in block
    assert len(block) < 2400


def test_persona_chat_replaces_fabricated_recommendations_with_grounded_candidates():
    from javstory.persona.persona_chat import (
        _deterministic_recommendation_response,
        _recommendation_candidates_from_payload,
        _recommendation_response_needs_replacement,
    )

    payload = {
        "messages": [
            {
                "role": "system",
                "content": "\n".join(
                    [
                        "[추천 후보 고정 근거]",
                        "recent_recommended_product_codes: OLD-001",
                        "library_search.results:",
                        "- 후보 1 product_code: ABC-123",
                        "  title_ko: 테스트 추천작",
                        "  actors: 배우A",
                        "  genres: 드라마",
                        "  ranking_reasons: sensual_summary/turn_ons 키워드 매칭",
                        "  matched_persona_terms: 긴장감",
                    ]
                ),
            }
        ]
    }
    candidates, recent_codes = _recommendation_candidates_from_payload(payload)
    fabricated = "1. **(신규 코드: 공개적 굴복)**: 후보 밖 작품을 추천할게."

    assert candidates[0]["product_code"] == "ABC-123"
    assert recent_codes == ["OLD-001"]
    assert _recommendation_response_needs_replacement("다른 작품 추천해", fabricated, candidates, recent_codes)

    replacement = _deterministic_recommendation_response("다른 작품 추천해", candidates, recent_codes)
    assert "ABC-123" in replacement
    assert "신규 코드" not in replacement


def test_persona_chat_replaces_recommendation_when_no_candidates():
    from javstory.persona.persona_chat import _recommendation_response_needs_replacement

    assert _recommendation_response_needs_replacement(
        "오늘의 작품 추천",
        "분위기 코드로는 숙모의 치명적 관능미가 좋아.",
        [],
        [],
    ) is True


def test_persona_chat_build_messages_uses_focused_context(monkeypatch):
    from javstory.persona import persona_chat as pc

    class DummyEngine:
        def build_chat_context(self, *_args, **_kwargs):
            return {
                "persona": {"summary": "전체 페르소나", "turn_ons": ["마사지"]},
                "taste_context": {},
                "mentioned_products": [],
                "library_search": {"results": []},
            }

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {}

        def load_recent_messages(self):
            return []

    monkeypatch.setattr(
        pc,
        "build_focused_context",
        lambda user_message, full_persona_data: "[취향 정보]\n- summary: 압축됨",
    )
    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_EMBED_FOCUS", "1")

    service = pc.PersonaChatService(engine=DummyEngine(), enhanced_memory_store=DummyMemory())
    messages = service.build_messages("마사지 취향 분석")
    # 통합 후 system 메시지는 messages[0] 하나 (역할+컨텍스트+메모리 통합)
    system_message = messages[0]["content"]

    assert "압축됨" in system_message
    assert "전체 페르소나" not in system_message


def test_persona_chat_story_summary_pins_exact_product_context(monkeypatch):
    from javstory.persona import persona_chat as pc

    class DummyEngine:
        def build_chat_context(self, *_args, **_kwargs):
            return {
                "persona": {"summary": "전체 페르소나", "turn_ons": ["마사지"]},
                "taste_context": {},
                "mentioned_products": [
                    {
                        "product_code": "ABC-123",
                        "title_ko": "테스트 작품",
                        "title_ja": "テスト作品",
                        "actors": ["배우A"],
                        "genres": ["드라마"],
                        "synopsis": "공식 시놉시스 내용",
                        "story_context": {
                            "summary": "Grok이 저장한 정확한 스토리 요약",
                            "tags": ["긴장감"],
                            "tones": ["차분함"],
                        },
                    }
                ],
                "library_search": {
                    "results": [
                        {
                            "product_code": "WRONG-999",
                            "title_ko": "다른 후보",
                            "grok": {"summary": "다른 작품 줄거리"},
                        }
                    ]
                },
            }

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {}

        def load_recent_messages(self):
            return []

    monkeypatch.setattr(pc, "build_focused_context", lambda *_args, **_kwargs: "[취향 정보]")

    service = pc.PersonaChatService(engine=DummyEngine(), enhanced_memory_store=DummyMemory())
    messages = service.build_messages("ABC-123 작품 설명해줘")
    # 통합 후: 컨텍스트·메모리 지시문이 모두 messages[0] 에 포함됨
    system_message = messages[0]["content"]

    assert "[작품 사실 고정 근거]" in system_message
    assert "ABC-123" in system_message
    assert "story_reliability: 높음" in system_message
    assert "story_source: DB synopsis + Grok story_context" in system_message
    assert "공식 시놉시스 내용" in system_message
    assert "Grok이 저장한 정확한 스토리 요약" in system_message
    assert "다른 검색 후보" in system_message
    assert "다른 작품 줄거리" not in system_message
    assert "[취향 정보]" not in system_message
    assert "사실 근거로 쓰지 않는다" in system_message


def test_persona_chat_story_context_only_is_marked_lower_confidence(monkeypatch):
    from javstory.persona import persona_chat as pc

    class DummyEngine:
        def build_chat_context(self, *_args, **_kwargs):
            return {
                "persona": {},
                "taste_context": {},
                "mentioned_products": [
                    {
                        "product_code": "ABC-123",
                        "title_ko": "테스트 작품",
                        "synopsis": "",
                        "story_context": {
                            "summary": "Grok 캐시 요약",
                            "source": "grok_story_cache",
                            "confidence": "medium",
                        },
                    }
                ],
                "library_search": {"results": []},
            }

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {}

        def load_recent_messages(self):
            return []

    service = pc.PersonaChatService(engine=DummyEngine(), enhanced_memory_store=DummyMemory())
    messages = service.build_messages("ABC-123 작품 설명해줘")
    system_message = messages[0]["content"]

    assert "story_reliability: 중간" in system_message
    assert "story_source: Grok story_context only" in system_message
    assert "공식 줄거리처럼 말하지 않는다" in system_message


def test_persona_chat_final_only_prompt_blocks_parenthetical_stage_direction(monkeypatch):
    from javstory.persona import persona_chat as pc

    class DummyEngine:
        def build_chat_context(self, *_args, **_kwargs):
            return {"persona": {}, "taste_context": {}, "mentioned_products": [], "library_search": {"results": []}}

    class DummyMemory:
        def load_from_json(self, *_args, **_kwargs):
            return None

        def prompt_context(self, *_args, **_kwargs):
            return {}

        def load_recent_messages(self):
            return []

    monkeypatch.setattr(pc, "build_focused_context", lambda *_args, **_kwargs: "[취향 정보]")

    service = pc.PersonaChatService(engine=DummyEngine(), enhanced_memory_store=DummyMemory())
    messages = service.build_messages("더 세게 말해줘", force_final_only=True)

    assert any("괄호로 된 행동 지문" in message["content"] for message in messages)


def test_persona_chat_close_session_compresses_enhanced_memory(tmp_path, monkeypatch):
    from javstory.persona import persona_chat as pc
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    path = tmp_path / "persona_chat_enhanced_memory.json"
    memory = EnhancedPersonaMemory()
    for idx in range(3):
        memory.add_turn(f"마사지 취향 {idx}", f"기억할게 {idx}")
    memory.save_to_json(str(path))

    monkeypatch.setattr(pc, "ENHANCED_PERSONA_MEMORY_PATH", path)
    monkeypatch.setattr(
        EnhancedPersonaMemory,
        "_summarize_session_with_llm",
        lambda self, turns: {
            "summary": "마사지 취향 세션",
            "new_preferences": ["마사지"],
            "important_context": ["긴장감"],
            "special_requests": [],
        },
    )

    service = pc.PersonaChatService()
    service.close_session()

    loaded = EnhancedPersonaMemory()
    loaded.load_from_json(str(path))
    assert loaded.working_memory == []
    assert loaded.episodic_memory[-1]["summary"] == "마사지 취향 세션"
    assert loaded.episodic_memory[-1]["turn_count"] == 3


def test_persona_chat_close_session_skips_short_working_memory(tmp_path, monkeypatch):
    from javstory.persona import persona_chat as pc
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    path = tmp_path / "persona_chat_enhanced_memory.json"
    memory = EnhancedPersonaMemory()
    memory.add_turn("한 턴", "응답")
    memory.add_turn("두 턴", "응답")
    memory.save_to_json(str(path))

    monkeypatch.setattr(pc, "ENHANCED_PERSONA_MEMORY_PATH", path)
    service = pc.PersonaChatService()
    service.close_session()

    loaded = EnhancedPersonaMemory()
    loaded.load_from_json(str(path))
    assert len(loaded.working_memory) == 2
    assert loaded.episodic_memory == []


def test_persona_chat_replaces_repetitive_single_code_recommendation():
    from javstory.persona.persona_chat import _recommendation_response_needs_replacement

    candidates = [
        {"product_code": "DEAB-002"},
        {"product_code": "HUNTB-066"},
    ]
    content = (
        "**DEAB-002** — 테스트 작품\n"
        "**DEAB-002**의 제목 래.\n"
        "**DEAB-002**의 배우 래.\n"
        "**DEAB-002**의 거유 래.\n"
        "**DEAB-002**의 단독작품 래.\n"
        "**DEAB-002**의 제 아내를"
    )

    assert _recommendation_response_needs_replacement("오늘의 작품 추천", content, candidates, []) is True


def test_persona_chat_ignores_truncated_candidate_codes():
    from javstory.persona.persona_chat import _recommendation_candidates_from_payload

    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "[추천 후보 고정 근거]\n"
                    "library_search.results:\n"
                    "- 후보 1 product_code: ABP-721\n"
                    "  title_ko: 정상 후보\n"
                    "- 후보 2 product_code: SA...\n"
                    "  title_ko: 잘린 후보\n"
                ),
            }
        ]
    }

    candidates, _recent = _recommendation_candidates_from_payload(payload)

    assert [item["product_code"] for item in candidates] == ["ABP-721"]
