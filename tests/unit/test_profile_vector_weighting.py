from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_weighted_average_vectors_favors_high_weight_seed():
    from javstory.library.embeddings.similarity import weighted_average_vectors

    low = [0.0, 0.0, 1.0]
    high = [1.0, 0.0, 0.0]
    result = weighted_average_vectors([low, high], [1.0, 9.0])
    assert result is not None
    assert result[0] > result[2]


def test_build_weighted_user_profile_vector_uses_seed_weights(monkeypatch):
    from javstory.library.embeddings import similarity as sim

    vectors = {
        "LOW-001": [0.0, 1.0],
        "HIGH-001": [1.0, 0.0],
    }
    monkeypatch.setattr(
        sim,
        "_vector_for_product_code",
        lambda pc, model: vectors.get(pc),
    )

    profile = sim.build_weighted_user_profile_vector(
        model="dummy",
        seed_codes=["LOW-001", "HIGH-001"],
        seed_weights=[1.0, 10.0],
    )
    assert profile is not None
    assert profile[0] > profile[1]


def test_build_negative_profile_vector_averages_disliked_seeds(monkeypatch):
    from javstory.library.embeddings import similarity as sim

    monkeypatch.setattr(
        sim,
        "_vector_for_product_code",
        lambda pc, model: [1.0, 0.0] if pc == "BAD-001" else [0.0, 1.0],
    )
    profile = sim.build_negative_profile_vector(
        model="dummy",
        seed_codes=["BAD-001", "BAD-002"],
    )
    assert profile == pytest.approx([0.5, 0.5])


def test_rank_unwatched_with_contrast_penalizes_negative_similarity(monkeypatch):
    from javstory.library.embeddings import similarity as sim

    monkeypatch.setattr(
        sim,
        "rank_unwatched_by_vector",
        lambda profile_vec, **kwargs: [
            sim.SimilarResult("GOOD-001", 0.9, MagicMock(), ["취향 프로필 유사"]),
            sim.SimilarResult("BAD-001", 0.88, MagicMock(), ["취향 프로필 유사"]),
        ],
    )
    monkeypatch.setattr(
        sim,
        "_vector_for_product_code",
        lambda pc, model: [1.0, 0.0] if pc == "BAD-001" else [0.0, 1.0],
    )

    ranked = sim.rank_unwatched_with_contrast(
        [0.0, 1.0],
        [1.0, 0.0],
        model="dummy",
        exclude_codes=set(),
        top_k=2,
        neg_lambda=0.5,
        min_score=0.0,
    )
    assert [item.product_code for item in ranked] == ["GOOD-001", "BAD-001"]
    assert ranked[0].score > ranked[1].score


def test_cluster_seed_vectors_returns_multiple_centroids(monkeypatch):
    from javstory.library.embeddings import similarity as sim

    vectors = {
        "A-001": [1.0, 0.0, 0.0],
        "A-002": [0.9, 0.1, 0.0],
        "B-001": [0.0, 1.0, 0.0],
        "B-002": [0.0, 0.9, 0.1],
        "C-001": [0.0, 0.0, 1.0],
        "C-002": [0.1, 0.0, 0.9],
        "D-001": [0.8, 0.2, 0.0],
        "D-002": [0.0, 0.8, 0.2],
    }
    monkeypatch.setattr(
        sim,
        "_vector_for_product_code",
        lambda pc, model: vectors.get(pc),
    )

    clusters = sim.cluster_seed_vectors(list(vectors.keys()), model="dummy", k=3)
    assert len(clusters) >= 2
    all_codes = {code for codes, _ in clusters for code in codes}
    assert len(all_codes) == len(vectors)


def test_merge_round_robin_ranked_interleaves_clusters():
    from javstory.library.embeddings.similarity import SimilarResult, merge_round_robin_ranked

    first = [
        SimilarResult("A-001", 0.9, MagicMock(), []),
        SimilarResult("A-002", 0.8, MagicMock(), []),
    ]
    second = [
        SimilarResult("B-001", 0.85, MagicMock(), []),
        SimilarResult("B-002", 0.75, MagicMock(), []),
    ]
    merged = merge_round_robin_ranked([first, second], limit=4)
    assert [item.product_code for item in merged] == ["A-001", "B-001", "A-002", "B-002"]


def test_recommendations_via_embeddings_sparse_seed_single_vector_path(monkeypatch):
    from javstory.analytics import preference_engine as pe

    histories = []
    for idx, code in enumerate(["POS-001", "POS-002", "POS-003"]):
        histories.append(
            MagicMock(
                product_code=code,
                liked=True,
                is_completed=False,
                rating=5,
                disliked=False,
                total_duration=100,
                watch_duration=100,
                updated_at=None,
            )
        )

    monkeypatch.setattr(pe, "_collect_embedding_seed_histories", lambda limit=30: histories)
    monkeypatch.setattr(
        pe,
        "_split_positive_negative_seeds",
        lambda _histories: (
            ["POS-001", "POS-002", "POS-003"],
            [3.0, 2.0, 1.0],
            [],
            [],
        ),
    )

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

    monkeypatch.setattr(pe, "get_db_session_ctx", lambda: DummySession())

    called = {"cluster": False, "contrast": False}

    def fake_cluster(*args, **kwargs):
        called["cluster"] = True
        return []

    def fake_contrast(*args, **kwargs):
        called["contrast"] = True
        return [MagicMock(product_code="REC-001", score=0.8, match_reasons=["취향 프로필 유사"])]

    import javstory.library.embeddings.similarity as sim

    monkeypatch.setattr(sim, "cluster_seed_vectors", fake_cluster)
    monkeypatch.setattr(sim, "build_weighted_user_profile_vector", lambda **kwargs: [1.0, 0.0])
    monkeypatch.setattr(sim, "build_negative_profile_vector", lambda **kwargs: None)
    monkeypatch.setattr(sim, "rank_unwatched_with_contrast", fake_contrast)

    with patch.object(DummySession, "query") as mock_query:
        meta = MagicMock(
            product_code="REC-001",
            title_ko="추천작",
            cover_image_local_path="",
            actors_ko="",
            release_date="",
        )
        mock_query.return_value.filter.return_value.all.return_value = [meta]
        out = pe._recommendations_via_embeddings(3, "dummy")

    assert called["cluster"] is False
    assert called["contrast"] is True
    assert out and out[0]["product_code"] == "REC-001"


def test_recommendations_via_embeddings_cluster_path_when_many_seeds(monkeypatch):
    from javstory.analytics import preference_engine as pe

    positive = [f"POS-{idx:03d}" for idx in range(8)]
    monkeypatch.setattr(
        pe,
        "_split_positive_negative_seeds",
        lambda _histories: (positive, [1.0] * 8, [], []),
    )
    monkeypatch.setattr(pe, "_collect_embedding_seed_histories", lambda limit=30: [])

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

    monkeypatch.setattr(pe, "get_db_session_ctx", lambda: DummySession())

    called = {"cluster": False}

    import javstory.library.embeddings.similarity as sim

    def fake_cluster(*args, **kwargs):
        called["cluster"] = True
        return [
            (positive[:4], [1.0, 0.0]),
            (positive[4:], [0.0, 1.0]),
        ]

    monkeypatch.setattr(sim, "cluster_seed_vectors", fake_cluster)
    monkeypatch.setattr(sim, "build_negative_profile_vector", lambda **kwargs: None)
    monkeypatch.setattr(
        sim,
        "rank_unwatched_with_contrast",
        lambda *args, **kwargs: [
            sim.SimilarResult("REC-001", 0.9, MagicMock(), []),
        ],
    )
    monkeypatch.setattr(
        sim,
        "merge_round_robin_ranked",
        lambda lists, limit: lists[0],
    )

    meta = MagicMock(
        product_code="REC-001",
        title_ko="클러스터 추천",
        cover_image_local_path="",
        actors_ko="",
        release_date="",
    )
    with patch.object(DummySession, "query") as mock_query:
        mock_query.return_value.filter.return_value.all.return_value = [meta]
        out = pe._recommendations_via_embeddings(3, "dummy")

    assert called["cluster"] is True
    assert out and out[0]["product_code"] == "REC-001"
