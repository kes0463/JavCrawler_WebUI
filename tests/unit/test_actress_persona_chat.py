from __future__ import annotations


def test_actress_name_span_candidates_strips_particles_and_request_tail():
    from javstory.persona.actress_query import actress_name_span_candidates

    spans = actress_name_span_candidates("카토 모에 작품 추천해 줘")
    assert "카토 모에" in spans

    spans2 = actress_name_span_candidates("나는 카토 모에가 좋아")
    assert "카토 모에" in spans2


def test_actress_db_chat_context_resolves_mentioned_name(monkeypatch):
    from javstory.persona.erotic_persona_engine import _actress_db_chat_context

    def _fake_resolve(message, *, extra_names=None, limit=3):
        for name in extra_names or []:
            if name in message:
                return [{
                    "id": 7,
                    "name": name,
                    "name_ja": "テスト",
                    "memo": "테스트 메모",
                    "profile_text": "프로필 본문",
                    "genres": "드라마",
                    "work_count": 12,
                }]
        if "카토 모에" in message:
            return [{
                "id": 9,
                "name": "카토 모에",
                "name_ja": "加藤もえ",
                "work_count": 4,
            }]
        return []

    monkeypatch.setattr(
        "javstory.persona.actress_query.resolve_actresses_from_message",
        _fake_resolve,
    )

    ctx = _actress_db_chat_context(
        "테스트배우 취향 어때?",
        {
            "favorite_actress_profiles": [
                {"name": "테스트배우", "name_ja": "テスト"},
            ],
            "top_actors": [{"name": "다른배우", "score": 1}],
        },
    )

    assert len(ctx["mentioned"]) == 1
    assert ctx["mentioned"][0]["id"] == 7
    assert ctx["mentioned"][0]["work_count"] == 12

    ctx2 = _actress_db_chat_context("카토 모에 작품 추천해 줘", {})
    assert ctx2["mentioned"][0]["name"] == "카토 모에"


def test_actor_list_matches_actress():
    from javstory.persona.actress_query import actor_list_matches_actress

    filt = {"match_names": ["카토 모에", "加藤もえ"]}
    assert actor_list_matches_actress(["카토 모에", "남배우"], filt)
    assert not actor_list_matches_actress(["미노 스즈메"], filt)


def test_actress_factual_grounding_block_requires_filmography():
    from javstory.persona.persona_chat import _actress_factual_grounding_block

    block = _actress_factual_grounding_block(
        "카토 모에",
        {
            "actress_db_context": {
                "mentioned": [{"id": 1, "name": "카토 모에", "name_ja": "加藤もえ", "work_count": 2}],
            },
            "library_search": {
                "results": [
                    {
                        "product_code": "ABC-123",
                        "title_ko": "테스트 작품",
                        "actors": ["카토 모에"],
                    }
                ],
            },
        },
    )

    assert "[배우 사실 고정 근거]" in block
    assert "ABC-123" in block
    assert "만들지 않는다" in block


def test_recommendation_grounding_includes_actress_filter():
    from javstory.persona.persona_chat import _recommendation_grounding_block

    block = _recommendation_grounding_block(
        "카토 모에 작품 추천해 줘",
        {
            "library_search": {
                "results": [
                    {
                        "product_code": "ABC-123",
                        "title_ko": "테스트",
                        "actors": ["카토 모에"],
                        "genres": ["드라마"],
                    }
                ],
                "actress_filter": {
                    "name": "카토 모에",
                    "match_names": ["카토 모에", "加藤もえ"],
                },
            },
            "persona": {},
            "sensual_recommendation_focus": {},
        },
        {},
    )
    assert "actress_filter_name: 카토 모에" in block
    assert "출연작이어야" in block


def test_compact_chat_context_includes_actress_db():
    from javstory.persona.persona_chat import _compact_chat_context

    compact = _compact_chat_context(
        {
            "persona": {},
            "sensual_priority_context": {},
            "sensual_recommendation_focus": {},
            "taste_context": {},
            "mentioned_products": [],
            "library_search": {"results": []},
            "actress_db_context": {
                "favorite_profiles": [
                    {
                        "id": 1,
                        "name": "즐겨찾기",
                        "memo": "메모",
                        "profile_text": "프로필",
                        "genres": "로맨스",
                        "work_count": 5,
                    }
                ],
                "mentioned": [
                    {
                        "id": 2,
                        "name": "언급배우",
                        "name_ja": "言及",
                        "memo": "언급 메모",
                        "profile_text": "언급 프로필",
                        "genres": "드라마",
                        "work_count": 9,
                    }
                ],
            },
        },
        aggressive=False,
    )

    actress = compact.get("actress_db_context") or {}
    assert actress.get("mentioned")[0]["name"] == "언급배우"
    assert actress.get("favorite_profiles")[0]["work_count"] == 5
    assert "memo/profile_text" in (actress.get("instruction") or "")


def test_deterministic_focused_context_includes_actress_profiles():
    from javstory.persona.persona_chat import _deterministic_focused_context

    text = _deterministic_focused_context(
        {
            "persona": {"summary": "요약"},
            "sensual_priority_context": {},
            "sensual_recommendation_focus": {},
            "taste_context": {},
            "library_search": {"results": []},
            "actress_db_context": {
                "favorite_profiles": [],
                "mentioned": [
                    {
                        "name": "언급배우",
                        "name_ja": "言及",
                        "memo": "DB 메모",
                        "genres": "드라마",
                        "work_count": 3,
                    }
                ],
            },
        },
        compact=False,
    )

    assert "[배우 프로필 DB]" in text
    assert "언급배우" in text
    assert "works=3" in text
    assert "DB 메모" in text
