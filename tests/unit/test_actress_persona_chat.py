from __future__ import annotations


def test_actress_db_chat_context_resolves_mentioned_name(monkeypatch):
    from javstory.persona.erotic_persona_engine import _actress_db_chat_context

    monkeypatch.setattr(
        "javstory.utils.actress_profile.get_actress_context_by_name",
        lambda name: {
            "id": 7,
            "name": name,
            "name_ja": "テスト",
            "memo": "테스트 메모",
            "profile_text": "프로필 본문",
            "genres": "드라마",
            "work_count": 12,
        } if name == "테스트배우" else {},
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
