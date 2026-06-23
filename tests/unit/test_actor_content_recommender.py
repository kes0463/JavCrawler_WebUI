from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_recommend_favorite_actor_content_returns_unwatched_actor_works(monkeypatch):
    from javstory.analytics import actor_content_recommender as acr

    monkeypatch.setattr(
        acr,
        "_collect_favorite_actors",
        lambda limit=12: [
            {
                "name": "테스트배우",
                "actress_id": 1,
                "actor_pref": 8.0,
                "favorite_intensity": 7.0,
                "is_favorite": True,
            }
        ],
    )
    monkeypatch.setattr(
        acr,
        "_resolve_actress_ids",
        lambda actors: {1: actors[0]},
    )
    monkeypatch.setattr(
        acr,
        "_collect_unwatched_actor_works",
        lambda actress_ids, watched_codes: {
            "UNW-001": [{"actress_id": 1}],
            "WATCHED-001": [{"actress_id": 1}],
        },
    )
    monkeypatch.setattr(
        acr,
        "_build_content_profile_vector",
        lambda model: [1.0, 0.0],
    )

    import javstory.library.embeddings.similarity as sim

    monkeypatch.setattr(
        sim,
        "vector_for_product_code",
        lambda pc, model: [1.0, 0.0] if pc == "UNW-001" else [0.0, 1.0],
    )
    monkeypatch.setattr(sim, "cosine_similarity", lambda a, b: 0.9)

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, *_args, **_kwargs):
            q = MagicMock()
            q.all.return_value = [MagicMock(product_code="WATCHED-001")]
            q.filter.return_value = q
            return q

    monkeypatch.setattr(acr, "get_db_session_ctx", lambda: DummySession())

    meta = MagicMock(
        product_code="UNW-001",
        title_ko="미시청 작품",
        cover_image_local_path="cover.jpg",
        actors_ko="테스트배우",
        release_date="2024-01-01",
    )
    with patch.object(DummySession, "query") as mock_query:
        mock_query.return_value.filter.return_value.all.return_value = [meta]
        out = acr.recommend_favorite_actor_content(5, model="dummy")

    assert len(out) == 1
    assert out[0]["product_code"] == "UNW-001"
    assert out[0]["source"] == "actor_content"
    assert any("좋아하는 배우" in reason for reason in out[0]["match_reasons"])


def test_recommend_favorite_actor_content_sorts_by_score(monkeypatch):
    from javstory.analytics import actor_content_recommender as acr

    monkeypatch.setattr(
        acr,
        "_collect_favorite_actors",
        lambda limit=12: [
            {
                "name": "배우A",
                "actress_id": 1,
                "actor_pref": 10.0,
                "favorite_intensity": 8.0,
                "is_favorite": True,
            }
        ],
    )
    monkeypatch.setattr(acr, "_resolve_actress_ids", lambda actors: {1: actors[0]})
    monkeypatch.setattr(
        acr,
        "_collect_unwatched_actor_works",
        lambda actress_ids, watched_codes: {
            "LOW-001": [{"actress_id": 1}],
            "HIGH-001": [{"actress_id": 1}],
        },
    )
    monkeypatch.setattr(acr, "_build_content_profile_vector", lambda model: [1.0, 0.0])

    import javstory.library.embeddings.similarity as sim

    def fake_vector(pc, model):
        return [1.0, 0.0] if pc == "HIGH-001" else [0.2, 0.8]

    monkeypatch.setattr(sim, "vector_for_product_code", fake_vector)
    monkeypatch.setattr(
        sim,
        "cosine_similarity",
        lambda a, b: 0.95 if b[0] > b[1] else 0.2,
    )

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, *_args, **_kwargs):
            q = MagicMock()
            q.all.return_value = []
            q.filter.return_value = q
            return q

    monkeypatch.setattr(acr, "get_db_session_ctx", lambda: DummySession())

    metas = [
        MagicMock(
            product_code="LOW-001",
            title_ko="낮은 점수",
            cover_image_local_path="",
            actors_ko="배우A",
            release_date="",
        ),
        MagicMock(
            product_code="HIGH-001",
            title_ko="높은 점수",
            cover_image_local_path="",
            actors_ko="배우A",
            release_date="",
        ),
    ]
    with patch.object(DummySession, "query") as mock_query:
        mock_query.return_value.filter.return_value.all.return_value = metas
        out = acr.recommend_favorite_actor_content(5, model="dummy")

    assert [row["product_code"] for row in out] == ["HIGH-001", "LOW-001"]
    assert out[0]["rec_score"] > out[1]["rec_score"]


def test_recommend_favorite_actor_content_empty_without_favorite_actors(monkeypatch):
    from javstory.analytics import actor_content_recommender as acr

    monkeypatch.setattr(acr, "_collect_favorite_actors", lambda limit=12: [])
    monkeypatch.setattr(acr, "_resolve_actress_ids", lambda actors: {})

    assert acr.recommend_favorite_actor_content(5, model="dummy") == []


def test_fetch_recommendation_pool_prioritizes_actor_content(monkeypatch):
    from javstory.persona import recommendation_pool as pool

    monkeypatch.setattr(pool, "_embeddings_enabled", lambda: True)
    monkeypatch.setattr(
        pool.HybridLibrarySearch,
        "search_with_fusion",
        lambda self, query: [],
    )
    monkeypatch.setattr(
        "javstory.analytics.actor_content_recommender.recommend_favorite_actor_content",
        lambda limit, model=None: [
            {
                "product_code": "ACT-001",
                "title_ko": "배우 추천",
                "rec_score": 0.82,
                "source": "actor_content",
            }
        ],
    )
    monkeypatch.setattr(
        "javstory.analytics.preference_engine.get_recommendations",
        lambda n, use_embeddings=True: [
            {"product_code": "GEN-001", "title_ko": "일반 추천", "rec_score": 0.7, "source": "embedding"}
        ],
    )

    results = pool.fetch_recommendation_pool("좋아하는 배우 작품 추천해줘", top_k=5)
    assert results
    assert results[0]["id"] == "ACT-001"
