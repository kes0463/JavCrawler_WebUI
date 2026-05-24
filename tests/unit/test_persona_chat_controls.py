from __future__ import annotations


def test_persona_chat_dynamic_temperature_and_tokens():
    from javstory.persona.persona_chat import _situational_max_tokens, _situational_temperature

    assert _situational_temperature("오늘은 일반 대화로 말해줘", 1.05) == 1.05
    assert _situational_temperature("더 야하게 롤플레이 톤으로 분석해줘", 1.05) == 1.22
    assert _situational_temperature("품번 정보 찾아줘", 1.05) == 0.9

    assert _situational_max_tokens("짧게 요약해줘", 2000) == 800
    assert _situational_max_tokens("더 세게 자세히 분석해줘", 2000) == 2000
    assert _situational_max_tokens("비슷한 추천 자세히", 2000) == 1700


def test_persona_chat_filters_reasoning_only_payload():
    from javstory.persona.persona_chat import _coalesce_response_text, _strip_reasoning_leak

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
