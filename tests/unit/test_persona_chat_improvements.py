from __future__ import annotations


def test_is_user_rating_list_request_detects_rating_list_queries():
    from javstory.persona.user_rating_list import is_user_rating_list_request

    assert is_user_rating_list_request("내가 점수 준 작품 리스트 알려줘")
    assert is_user_rating_list_request("별점 부여한 작품 목록 보여줘")
    assert not is_user_rating_list_request("비슷한 작품 추천해줘")


def test_user_rating_list_grounding_block_pins_watch_history_rows(monkeypatch):
    from javstory.persona.persona_chat import _user_rating_list_grounding_block

    ctx = {
        "user_rating_list": [
            {
                "product_code": "HBAD-509",
                "title_ko": "테스트 작품",
                "user_rating": 5,
                "user_liked": True,
                "user_is_completed": False,
                "actors": ["배우A"],
                "genres": ["드라마"],
            }
        ]
    }
    block = _user_rating_list_grounding_block("내가 점수 준 작품 알려줘", ctx)
    assert "HBAD-509" in block
    assert "user_rating: 5" in block
    assert "목록에 없는 작품은 절대 추가하지 않는다" in block


def test_deterministic_rating_list_response_empty():
    from javstory.persona.persona_chat import _deterministic_rating_list_response

    text = _deterministic_rating_list_response([])
    assert "아직" in text
    assert "점수" in text


def test_apply_personalized_ranking_hard_excludes_recent_recommendations():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    ctx = {
        "library_search": {
            "query": "추천해줘",
            "results": [
                {"product_code": "AAA-111", "score": 0.9, "title_ko": "A"},
                {"product_code": "BBB-222", "score": 0.8, "title_ko": "B"},
            ],
            "source_policy": {"mode": "taste_recommendation"},
        },
        "persona": {"sensual_summary": "긴장감", "turn_ons": ["긴장감"]},
        "sensual_recommendation_focus": {"summary": "긴장감", "turn_ons": ["긴장감"]},
    }
    memory = {"recent_recommended_product_codes": ["AAA-111"], "strong_reaction_notes": [], "negative_feedback_notes": []}
    out = _apply_personalized_ranking(ctx, memory)
    codes = [item["product_code"] for item in out["library_search"]["results"]]
    assert "AAA-111" not in codes
    assert "BBB-222" in codes


def test_diversify_ranked_results_prefers_genre_diversity():
    from javstory.persona import persona_chat as pc

    ranked = [
        {"product_code": "AAA-1", "persona_match_score": 90, "genres": ["드라마"], "actors": ["A"], "score": 1.0},
        {"product_code": "AAA-2", "persona_match_score": 89, "genres": ["드라마"], "actors": ["A"], "score": 0.9},
        {"product_code": "BBB-1", "persona_match_score": 70, "genres": ["코미디"], "actors": ["B"], "score": 0.8},
    ]
    diversified = pc._diversify_ranked_results(ranked, pool_size=2)
    top_codes = [item["product_code"] for item in diversified[:2]]
    assert top_codes[0] == "AAA-1"
    assert "BBB-1" in top_codes
    assert "AAA-2" not in top_codes


def test_chat_intent_user_rating_list():
    from javstory.persona.erotic_persona_engine import _chat_intent

    assert _chat_intent("내가 점수 준 작품 리스트 알려줘", []) == "user_rating_list"


def test_needs_hybrid_library_search_skips_general_and_self_analysis():
    from javstory.persona.erotic_persona_engine import _needs_hybrid_library_search

    assert _needs_hybrid_library_search("general", "왜 그런 취향이야?") is False
    assert _needs_hybrid_library_search("self_analysis", "내 취향 분석해줘") is False
    assert _needs_hybrid_library_search("recommendation", "비슷한 작품 추천해줘") is True
    assert _needs_hybrid_library_search("general", "이런 작품 찾아줘") is True


def test_chat_pipeline_mode_general_is_light():
    from javstory.persona.erotic_persona_engine import _chat_pipeline_mode

    assert _chat_pipeline_mode("general", "안녕") == "light"


def test_persona_chat_stream_max_tokens_caps_output(monkeypatch):
    from javstory.persona.persona_chat import _persona_chat_stream_max_tokens

    monkeypatch.setenv("JAVSTORY_PERSONA_CHAT_STREAM_MAX_TOKENS", "900")
    assert _persona_chat_stream_max_tokens("긴장감 있는 작품 추천해줘", 2600) == 2200
    assert _persona_chat_stream_max_tokens("어떤 특징이 있어?", 2600) == 1900
    assert _persona_chat_stream_max_tokens("왜 그런 취향이야?", 2600) == 1800
    assert _persona_chat_stream_max_tokens("짧게 알려줘", 2600) == 800


def test_should_use_full_chat_pipeline_defaults_to_full_except_short_hints():
    from javstory.persona.persona_chat import _should_use_full_chat_pipeline

    assert _should_use_full_chat_pipeline("왜 그런 취향이야?")
    assert _should_use_full_chat_pipeline("근친상간 작품 추천해줘")
    assert _should_use_full_chat_pipeline("어떤 특징이 있어?")
    assert not _should_use_full_chat_pipeline("짧게 알려줘")


def test_recommendation_response_too_thin_detects_one_line_list():
    from javstory.persona.persona_chat import (
        _looks_like_placeholder_product_codes,
        _recommendation_response_needs_replacement,
        _recommendation_response_too_thin,
    )

    thin = (
        "1. ABC-456 — 유부녀의 절정 (주부, 유부녀)\n"
        "2. ABC-789 — 압도적인 신체적 자극 (거유)"
    )
    codes = ["ABC-456", "ABC-789"]
    assert _looks_like_placeholder_product_codes(codes)
    assert _recommendation_response_too_thin(thin, codes)
    candidates = [{"product_code": "START-498", "title_ko": "테스트", "actors": "배우A", "genres": "드라마"}]
    assert _recommendation_response_needs_replacement("오늘 볼만한 작품 추천해", thin, candidates, [])


def test_deterministic_recommendation_response_includes_detail_fields():
    from javstory.persona.persona_chat import _deterministic_recommendation_response

    candidates = [
        {
            "product_code": "START-498",
            "title_ko": "테스트 작품",
            "actors": "배우A, 배우B",
            "genres": "드라마, 유부녀",
            "synopsis": "가족 관계 속에서 벌어지는 긴장감 있는 이야기",
            "ranking_reasons": "sensual_summary/turn_ons 키워드 매칭",
            "matched_persona_terms": "긴장감",
        }
    ]
    text = _deterministic_recommendation_response("오늘 볼만한 작품 추천해", candidates, [])
    assert "START-498" in text
    assert "배우:" in text
    assert "한줄 요약:" in text
    assert "추천 이유:" in text
    assert "ABC-456" not in text


def test_is_actor_recommendation_intent_matches_named_work_request(monkeypatch):
    from javstory.persona.recommendation_pool import _is_actor_recommendation_intent

    monkeypatch.setattr(
        "javstory.persona.actress_query.resolve_actress_by_name",
        lambda name: 1 if name == "카토 모에" else None,
    )
    assert _is_actor_recommendation_intent("카토 모에 작품 추천해 줘")
    assert not _is_actor_recommendation_intent("오늘 볼만한 작품 추천해 줘")


def test_fetch_recommendation_pool_uses_sql_path_without_embedding_weights(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    calls: list[str] = []

    class DummySearch:
        def __init__(self, *, limit: int):
            calls.append(f"limit={limit}")

        def search(self, query: str, **kwargs):
            return {
                "results": [
                    {
                        "product_code": "TST-001",
                        "title_ko": "테스트",
                        "score": 0.9,
                        "source": "title",
                    }
                ]
            }

    monkeypatch.setattr(
        "javstory.persona.library_search.PersonaLibrarySearch",
        DummySearch,
    )
    monkeypatch.setattr(
        pool.HybridLibrarySearch,
        "search_with_fusion",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not use hybrid fusion")),
    )
    monkeypatch.setattr(pool, "_taste_recommendation_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_semantic_profile_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_actor_content_channel", lambda *args, **kwargs: [])
    pool.clear_session_pool_cache()

    results = pool.fetch_recommendation_pool(
        "비슷한 작품 추천해줘",
        top_k=5,
        pool_k=5,
        weights=(0.45, 0.0, 0.55),
    )
    assert results[0]["id"] == "TST-001"
    assert calls == ["limit=5"]


def test_fetch_recommendation_pool_rrf_merges_channels(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    monkeypatch.setattr(pool, "_work_embeddings_enabled", lambda: False)
    monkeypatch.setattr(
        pool,
        "_search_persona_library",
        lambda query, *, top_k, fast=True: [
            {"id": "SQL-001", "title": "SQL", "score": 0.9, "source": "persona_sql"},
            {"id": "BOTH-001", "title": "Both", "score": 0.8, "source": "persona_sql"},
        ],
    )
    monkeypatch.setattr(
        pool,
        "_taste_recommendation_channel",
        lambda limit, exclude: [
            {"id": "TASTE-001", "title": "Taste", "score": 0.95, "source": "taste_embedding"},
            {"id": "BOTH-001", "title": "Both", "score": 0.85, "source": "taste_embedding"},
        ],
    )
    monkeypatch.setattr(pool, "_semantic_profile_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_actor_content_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_hidden_gems_channel", lambda *args, **kwargs: [])

    results = pool.fetch_recommendation_pool("추천해줘", top_k=4, pool_k=4)
    ids = [item["id"] for item in results]
    assert "BOTH-001" in ids
    assert ids[0] == "BOTH-001"
    assert len(ids) == 3


def test_fetch_recommendation_pool_expands_pool_k_by_default(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    monkeypatch.setattr(pool, "_work_embeddings_enabled", lambda: False)
    seen: list[int] = []

    def _capture_sql(query, *, top_k, fast=True):
        seen.append(top_k)
        return [{"id": "ONLY-001", "title": "Only", "score": 1.0, "source": "persona_sql"}]

    monkeypatch.setattr(pool, "_search_persona_library", _capture_sql)
    monkeypatch.setattr(pool, "_taste_recommendation_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_semantic_profile_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_actor_content_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_hidden_gems_channel", lambda *args, **kwargs: [])

    pool.fetch_recommendation_pool("추천해줘", top_k=5)
    assert seen == [20]


def test_recommendation_search_sizes_full_recommendation():
    from javstory.persona.erotic_persona_engine import _recommendation_search_sizes

    top_k, pool_k = _recommendation_search_sizes("recommendation", "full", compact=False, fast=False)
    assert top_k == 24
    assert pool_k == 80
    light_top, light_pool = _recommendation_search_sizes("recommendation", "light", compact=False, fast=False)
    assert light_top == 8
    assert light_pool == 32


def test_fetch_recommendation_pool_session_cache(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    pool.clear_session_pool_cache()
    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    monkeypatch.setattr(pool, "_work_embeddings_enabled", lambda: False)
    calls = {"n": 0}

    def _sql(query, *, top_k, fast=True):
        calls["n"] += 1
        return [{"id": "CACHE-001", "title": "Cached", "score": 1.0, "source": "persona_sql"}]

    monkeypatch.setattr(pool, "_search_persona_library", _sql)
    monkeypatch.setattr(pool, "_taste_recommendation_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_semantic_profile_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_actor_content_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pool, "_hidden_gems_channel", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "javstory.library.embeddings.priority_queue.ensure_priority_embeddings_async",
        lambda *args, **kwargs: None,
    )

    key = pool.build_session_pool_key("추천해줘", exclude_codes=["AAA-111"], seed_codes=["BBB-222"])
    first = pool.fetch_recommendation_pool("추천해줘", top_k=3, pool_k=3, session_key=key)
    second = pool.fetch_recommendation_pool("추천해줘", top_k=3, pool_k=3, session_key=key)
    assert first[0]["id"] == "CACHE-001"
    assert second[0]["id"] == "CACHE-001"
    assert calls["n"] == 1


def test_apply_exploration_mix_injects_hidden_gems():
    from javstory.persona.persona_chat import _apply_exploration_mix

    ranked = [
        {"product_code": f"TOP-{idx}", "persona_match_score": 90 - idx, "source": "persona_sql"}
        for idx in range(6)
    ] + [
        {"product_code": "GEM-001", "persona_match_score": 40, "source": "hidden_gem"},
        {"product_code": "GEM-002", "persona_match_score": 35, "source": "hidden_gem"},
    ]
    mixed = _apply_exploration_mix(ranked, epsilon=0.25)
    top_codes = [item["product_code"] for item in mixed[:8]]
    assert "GEM-001" in top_codes or "GEM-002" in top_codes


def test_empty_recommendation_explanation_mentions_diagnosis():
    from javstory.persona.persona_chat import _empty_recommendation_explanation

    text = _empty_recommendation_explanation(
        {
            "library_search": {
                "results": [],
                "source_policy": {"mode": "taste_recommendation"},
                "diversity_policy": {"recent_recommended_product_codes": ["AAA-111"]},
            }
        }
    )
    assert "후보" in text
    assert "최근" in text or "취향" in text


def test_sync_recommendation_watch_feedback_records_implicit_positive(monkeypatch):
    from javstory.persona.persona_memory import EnhancedPersonaMemory
    from javstory.persona.recommendation_feedback import sync_recommendation_watch_feedback

    memory = EnhancedPersonaMemory()
    memory.pending_recommendation_outcomes = [
        {"product_code": "REC-001", "recommended_at": "2020-01-01T00:00:00+00:00"}
    ]

    class _Row:
        product_code = "REC-001"
        rating = 5
        liked = True
        disliked = False
        watch_duration = 1200
        total_duration = 3600
        is_completed = True
        updated_at = __import__("datetime").datetime(2026, 1, 2, tzinfo=__import__("datetime").timezone.utc)

    monkeypatch.setattr(
        "javstory.persona.recommendation_feedback.get_db_session_ctx",
        lambda: _FakeSession(_Row()),
    )

    sync_recommendation_watch_feedback(memory)
    assert any("REC-001" in str(note.get("text") or "") for note in memory.strong_reaction_notes)
    assert memory.pending_recommendation_outcomes == []


class _FakeSession:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, _model):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return [self._row]


def test_user_profile_vector_cache_roundtrip(tmp_path, monkeypatch):
    from javstory.library.embeddings import user_profile_cache as cache

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        cache,
        "embeddings_ollama_model_from_env",
        lambda: "test-model",
    )
    monkeypatch.setattr(
        cache,
        "build_weighted_user_profile_vector",
        lambda **kwargs: [0.1, 0.2, 0.3],
        raising=False,
    )
    import javstory.library.embeddings.similarity as sim

    monkeypatch.setattr(sim, "build_weighted_user_profile_vector", lambda **kwargs: [0.1, 0.2, 0.3])

    first = cache.resolve_weighted_user_profile_vector(["AAA-111", "BBB-222"], [1.0, 2.0], model="test-model")
    second = cache.resolve_weighted_user_profile_vector(["AAA-111", "BBB-222"], [1.0, 2.0], model="test-model")
    assert first == [0.1, 0.2, 0.3]
    assert second == [0.1, 0.2, 0.3]


def test_enhanced_memory_tracks_recent_recommended_codes():
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    memory = EnhancedPersonaMemory()
    memory.record_turn("추천해줘", "1. **HBAD-509** — 테스트 작품")
    assert "HBAD-509" in memory.recent_recommended_product_codes


def test_remove_note_from_memory():
    from javstory.persona.persona_memory import EnhancedPersonaMemory

    memory = EnhancedPersonaMemory()
    memory.preference_notes = [{"text": "테스트", "created_at": "now"}]
    assert memory.remove_note("preference", 0) is True
    assert memory.preference_notes == []


def test_is_rated_works_analysis_request_detects_taste_pattern_queries():
    from javstory.persona.persona_chat import _is_rated_works_analysis_request

    assert _is_rated_works_analysis_request("내가 점수·좋아요·완주를 남긴 작품들의 특징을 분석해 보자")
    assert _is_rated_works_analysis_request("어떤 특징이 있어?")
    assert _is_rated_works_analysis_request("점수 준 작품 특징")
    assert not _is_rated_works_analysis_request("작품 추천해 줘")
    assert not _is_rated_works_analysis_request("마사지 취향 분석")


def test_fake_numeric_recommendation_triggers_replacement():
    from javstory.persona.persona_chat import (
        _deterministic_recommendation_response,
        _looks_like_fake_numeric_recommendation,
        _recommendation_response_needs_replacement,
    )

    fabricated = (
        "추천 작품은 다음과 같다.\n"
        "1. 374: 딸과 아버지의 성적인 관계가 주제로 등장하는 작품\n"
        "2. 721: 며느리와 장인의 관계가 주제로 등장하는 작품"
    )
    candidates = [{"product_code": "START-498", "title_ko": "테스트"}]
    assert _looks_like_fake_numeric_recommendation(fabricated)
    assert _recommendation_response_needs_replacement("작품 추천해 줘", fabricated, candidates, [])

    replacement = _deterministic_recommendation_response("작품 추천해 줘", candidates, [])
    assert "START-498" in replacement
    assert "374" not in replacement


def test_rated_works_analysis_grounding_block_includes_metadata():
    from javstory.persona.persona_chat import _rated_works_analysis_grounding_block

    ctx = {
        "user_rating_list": [
            {
                "product_code": "HBAD-509",
                "title_ko": "테스트",
                "user_rating": 5,
                "user_liked": True,
                "user_is_completed": False,
                "actors": ["배우A"],
                "genres": ["드라마", "가족"],
                "synopsis": "테스트 시놉",
            }
        ]
    }
    block = _rated_works_analysis_grounding_block("어떤 특징이 있어?", ctx)
    assert "HBAD-509" in block
    assert "드라마" in block
    assert "첫째로/둘째로" in block


def test_deterministic_rated_works_pattern_summary_uses_genres():
    from javstory.persona.persona_chat import (
        _deterministic_rated_works_pattern_summary,
        _rated_works_analysis_response_needs_replacement,
    )

    items = [
        {"product_code": "AAA-111", "genres": ["드라마", "가족"], "actors": ["배우A"]},
        {"product_code": "BBB-222", "genres": ["드라마"], "actors": ["배우A", "배우B"]},
    ]
    text = _deterministic_rated_works_pattern_summary(items)
    assert "드라마" in text
    assert "AAA-111" in text
    assert not _rated_works_analysis_response_needs_replacement("어떤 특징이 있어?", text)

    bureaucratic = "첫째로, 가족 구성원 간의 성적 상호작용. 둘째로, 주인공은 상대방의 성욕에 휘둘린다."
    assert _rated_works_analysis_response_needs_replacement("점수 준 작품 특징", bureaucratic)


def test_prefer_streamed_over_final_rejects_fake_recommendation_stream():
    from javstory.persona.persona_chat import _prefer_streamed_over_final

    streamed = "1. 374: 딸과 아버지\n2. 721: 며느리와 장인"
    final = "1. **START-498** — 테스트 작품"
    assert _prefer_streamed_over_final(streamed, final, user_message="작품 추천해 줘") == final

    good_stream = "1. **START-498** — 테스트 작품\n   배우A / 드라마\n   긴장감이 좋아."
    short_final = "1. **START-498** — 테스트"
    assert _prefer_streamed_over_final(good_stream, short_final, user_message="작품 추천해 줘") == good_stream


def test_extract_theme_query_terms_keeps_graduation_theme():
    from javstory.persona.library_search import extract_theme_query_terms

    assert extract_theme_query_terms("졸업식 작품 추천해 줘") == ["졸업식"]


def test_apply_personalized_ranking_hard_filters_theme_miss():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    ranked = _apply_personalized_ranking(
        {
            "library_search": {
                "query": "졸업식 작품 추천해 줘",
                "results": [
                    {
                        "product_code": "AAA-001",
                        "title_ko": "무관한 작품",
                        "genres": ["NTR"],
                        "score": 0.9,
                    },
                    {
                        "product_code": "BBB-002",
                        "title_ko": "졸업식 파티",
                        "synopsis": "졸업식 날 벌어지는 이야기",
                        "genres": ["학원"],
                        "score": 0.7,
                    },
                ],
            },
            "persona": {},
            "sensual_recommendation_focus": {},
        },
        {},
    )
    results = ranked["library_search"]["results"]
    assert len(results) == 1
    assert results[0]["product_code"] == "BBB-002"
    assert results[0]["matched_query_terms"] == ["졸업식"]


def test_fetch_recommendation_pool_theme_strict_skips_taste(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    taste_called = {"value": False}

    def _taste(*args, **kwargs):
        taste_called["value"] = True
        return [{"id": "TASTE-001", "title": "taste", "score": 0.9, "source": "taste"}]

    monkeypatch.setattr(pool, "_taste_recommendation_channel", _taste)
    monkeypatch.setattr(
        pool,
        "_search_persona_library",
        lambda query, *, top_k, fast=True: [
            {"id": "GRAD-001", "title": "졸업식", "score": 0.8, "source": "persona_sql"},
        ],
    )
    pool.clear_session_pool_cache()

    results = pool.fetch_recommendation_pool("졸업식 작품 추천해 줘", top_k=4, pool_k=4)
    assert taste_called["value"] is False
    assert results and results[0]["id"] == "GRAD-001"


def test_theme_search_ignores_recent_exclude_pollution(monkeypatch):
    from javstory.persona import recommendation_pool as pool
    from javstory.persona.persona_chat import PersonaChatService, _apply_personalized_ranking, _recent_assistant_product_codes

    captured: list[str] = []

    def _search(query, *, top_k, fast=True):
        captured.append(query)
        return [{"id": "JUQ-547", "title": "졸업식 이후", "score": 0.9, "source": "persona_sql"}]

    monkeypatch.setattr(pool, "_persona_chat_embeddings_enabled", lambda: False)
    monkeypatch.setattr(pool, "_search_persona_library", _search)
    pool.clear_session_pool_cache()

    polluted = (
        "졸업식 작품 추천해줘\n"
        "최근 챗에서 이미 추천한 품번은 후보에서 제외: SNR-004, SONE-560"
    )
    results = pool.fetch_recommendation_pool(polluted, top_k=4, pool_k=4)
    assert captured == ["졸업식"]
    assert results and results[0]["id"] == "JUQ-547"

    svc = PersonaChatService()
    recent = list(getattr(svc.enhanced_memory_store, "recent_recommended_product_codes", None) or [])[:12]
    ctx = svc.engine.build_chat_context(
        "졸업식 작품 추천해줘",
        recent_recommended_codes=recent,
        compact=True,
        memory_store=svc.enhanced_memory_store,
        fast=True,
    )
    ctx = _apply_personalized_ranking(
        ctx,
        {"recent_recommended_product_codes": recent},
    )
    codes = [item.get("product_code") for item in ctx["library_search"]["results"]]
    assert codes
    assert any("JUQ" in str(code or "") or "JUL" in str(code or "") or "IPX" in str(code or "") for code in codes)


def test_extract_recommendation_query_terms_keeps_theme_not_boilerplate():
    from javstory.persona.persona_chat import _extract_recommendation_query_terms

    assert _extract_recommendation_query_terms("근친상간 작품 추천해줘") == ["근친상간"]


def test_apply_personalized_ranking_prioritizes_explicit_genre_request():
    from javstory.persona.persona_chat import _apply_personalized_ranking

    ctx = {
        "library_search": {
            "query": "근친상간 작품 추천해줘",
            "results": [
                {
                    "product_code": "MIDV-713",
                    "score": 0.95,
                    "title_ko": "NTR 작품",
                    "genres": ["네토라레", "유부녀"],
                    "synopsis": "유부녀 이야기",
                },
                {
                    "product_code": "DLDSS-325",
                    "score": 0.7,
                    "title_ko": "근친 작품",
                    "genres": ["근친상간", "스토리"],
                    "synopsis": "아버지와 딸",
                },
            ],
            "source_policy": {"mode": "taste_recommendation"},
        },
        "persona": {"sensual_summary": "유부녀 거유", "turn_ons": ["유부녀", "거유"]},
        "sensual_recommendation_focus": {"summary": "유부녀 거유", "turn_ons": ["유부녀", "거유"]},
    }
    out = _apply_personalized_ranking(ctx, {})
    codes = [item["product_code"] for item in out["library_search"]["results"]]
    assert codes[0] == "DLDSS-325"
    assert out["library_search"]["query_focus_terms"] == ["근친상간"]


def test_recommendation_reason_omits_duplicate_synopsis():
    from javstory.persona.persona_chat import (
        _SYNOPSIS_SUMMARY_MAX_CHARS,
        _fallback_recommendation_reason,
        _recommendation_item_detail_lines,
    )

    long_synopsis = "첫 문장입니다. " + "가" * 300 + " 마지막 문장입니다."
    item = {
        "product_code": "DLDSS-325",
        "title_ko": "테스트",
        "genres": ["근친상간"],
        "synopsis": long_synopsis,
        "ranking_reasons": ["요청 장르/테마 매칭: 근친상간"],
        "matched_query_terms": ["근친상간"],
        "matched_persona_terms": ["거유"],
    }
    lines = _recommendation_item_detail_lines(item, 1)
    joined = "\n".join(lines)
    assert "한줄 요약:" in joined
    assert "   시놉:" not in joined
    summary_line = [line for line in lines if line.startswith("   한줄 요약:")][0]
    assert len(summary_line) <= len("   한줄 요약: ") + _SYNOPSIS_SUMMARY_MAX_CHARS + 3
    assert "가" * 100 not in summary_line
    reason = _fallback_recommendation_reason(item, include_synopsis=False)
    assert "시놉시스상" not in reason
    assert "근친상간" in reason
    assert "겹쳐요" in reason or "중심" in reason or "취향" in reason
    assert "랭킹 근거" not in reason
    assert "sensual_summary" not in reason
    assert "쪽이에요" not in reason
    assert "가" * 100 not in reason


def test_summarize_synopsis_prefers_grok_summary_over_raw_clip():
    from javstory.persona.persona_chat import _summarize_synopsis_for_display

    item = {
        "product_code": "TST-001",
        "synopsis": "가" * 300,
        "grok": {"summary": "첫 장면은 긴장감 있게 시작한다. 이후 관계가 점점 깊어진다."},
    }
    summary = _summarize_synopsis_for_display(item)
    assert "긴장감" in summary
    assert "가" * 50 not in summary


def test_summarize_synopsis_extracts_two_sentences_from_raw():
    from javstory.persona.persona_chat import _extract_summary_sentences

    text = "누나의 뒤태에 성욕이 터진다. 들키고 상황이 격해진다. 세 번째 문장은 버린다."
    summary = _extract_summary_sentences(text, max_sentences=2, max_chars=140)
    assert "누나" in summary
    assert "들키고" in summary
    assert "세 번째" not in summary


def test_recommendation_item_detail_uses_short_title_and_summary_label():
    from javstory.persona.persona_chat import _recommendation_item_detail_lines

    item = {
        "product_code": "LULU-384",
        "title_ko": "LULU-384 - 풍만한 엉덩이의 누나의 노출된 뒤태 도발에 억눌러왔던 성욕 폭발, 은밀히 옷깃을 적셨더니",
        "actors": "나나하라 사유",
        "genres": ["검열 완료", "누나·여동생", "근친상간", "단독작품"],
        "synopsis": "누나의 엉덩이가 정말 탐미로워...! 빨래를 널고 있는 누나의 풍만한 엉덩이에 억눌러왔던 성욕이 폭발한다.",
    }
    lines = _recommendation_item_detail_lines(item, 1)
    joined = "\n".join(lines)
    assert lines[0].startswith("1. **LULU-384** —")
    assert "LULU-384 -" not in lines[0]
    assert "   배우: 나나하라 사유" in lines
    assert "   장르: 누나·여동생, 근친상간" in lines
    assert "검열 완료" not in joined
    assert "단독작품" not in joined
    assert any(line.startswith("   한줄 요약:") for line in lines)
    assert not any(line.startswith("   시놉:") for line in lines)


def test_recommendation_reason_reads_like_natural_copy():
    from javstory.persona.persona_chat import (
        _FORMULAIC_REASON_PHRASES,
        _fallback_recommendation_reason,
    )

    item = {
        "product_code": "LULU-384",
        "title_ko": "LULU-384 - 풍만한 엉덩이의 누나의 노출된 뒤태 도발에 억눌러왔던 성욕 폭발",
        "genres": ["검열 완료", "누나·여동생", "근친상간", "단독작품"],
        "matched_persona_terms": ["풍만한", "거유"],
        "ranking_reasons": ["sensual_summary/turn_ons 키워드 매칭", "요청 장르/테마 매칭: 근친상간"],
        "matched_query_terms": ["근친상간"],
    }
    reason = _fallback_recommendation_reason(item, include_synopsis=False)
    assert "근친상간" in reason
    assert "거유" in reason or "풍만" in reason
    assert "LULU-384" not in reason
    assert "엉덩이" not in reason
    assert "랭킹" not in reason
    assert "turn_ons" not in reason
    assert "쪽이에요" not in reason
    assert not any(phrase in reason for phrase in _FORMULAIC_REASON_PHRASES)


def test_recommendation_reason_filters_broken_taste_fragments():
    from javstory.persona.persona_chat import _fallback_recommendation_reason

    item = {
        "product_code": "MIDV-699",
        "title_ko": "MIDV-699 테스트",
        "genres": ["미소녀", "근친상간"],
        "matched_persona_terms": ["오는", "있는", "미소녀"],
    }
    reason = _fallback_recommendation_reason(item, include_synopsis=False)
    assert "오는" not in reason
    assert "있는" not in reason
    assert "미소녀" in reason


def test_recommendation_reason_is_single_sentence_without_title_hook():
    from javstory.persona.persona_chat import _fallback_recommendation_reason

    item = {
        "product_code": "SDMF-037",
        "title_ko": "SDMF-037 육체노동자인 아빠는 비가 오면 일이 쉬어져서 딸인 나랑 아파트에서 계속 성교해요",
        "genres": ["제복", "여고생", "미소녀"],
        "matched_persona_terms": ["미소녀"],
        "synopsis": "육체노동자인 아빠는 비가 오면 일이 쉬어져서 딸인 나랑 아파트에서 계속 성교해요",
    }
    reason = _fallback_recommendation_reason(item, include_synopsis=False)
    assert reason.count("。") == 0
    assert reason.count(".") <= 1
    assert "육체노동" not in reason
    assert "미소녀" in reason


def test_recommendation_reason_notes_query_miss_without_internal_tags():
    from javstory.persona.persona_chat import _fallback_recommendation_reason

    item = {
        "product_code": "IPZZ-246",
        "title_ko": "IPZZ-246 BBQ NTR",
        "genres": ["미소녀", "거유", "음란", "NTR"],
        "matched_persona_terms": ["거유"],
        "matched_query_terms": ["근친상간"],
        "ranking_reasons": ["요청 키워드 미매칭 감점"],
    }
    reason = _fallback_recommendation_reason(item, include_synopsis=False)
    assert "미매칭" not in reason
    assert "감점" not in reason
    assert "거리" in reason or "맞아요" in reason
