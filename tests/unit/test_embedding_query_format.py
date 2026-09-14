"""query_format helpers for e5 instruct + concept coverage."""

from __future__ import annotations

import pytest

from javstory.library.embeddings.query_format import (
    blend_embedding_lexical_score,
    clear_concept_lexicon_cache,
    concept_coverage,
    expand_query_concepts,
    format_search_query_for_embedding,
    is_e5_mistral_model,
    is_known_concept_token,
)


def test_format_e5_mistral_instruct_query(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", "e5-mistral-7b-instruct-Q4_K_M")
    monkeypatch.delenv("JAVSTORY_EMBEDDING_QUERY_TEMPLATE", raising=False)
    out = format_search_query_for_embedding("비오는 사무실", model="e5-mistral-7b-instruct-Q4_K_M")
    assert out.startswith("Instruct:")
    assert out.endswith("Query: 비오는 사무실") or "Query: 비오는 사무실" in out
    assert is_e5_mistral_model("e5-mistral-7b-instruct-Q4_K_M")


def test_format_plain_model_unchanged(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", "nomic-embed-text")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", "")
    monkeypatch.delenv("JAVSTORY_EMBEDDING_QUERY_TEMPLATE", raising=False)
    assert format_search_query_for_embedding("hello", model="nomic-embed-text") == "hello"


def test_concept_coverage_requires_both_rain_and_office(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("비오는 사무실")
    assert len(concepts) >= 2
    only_office = concept_coverage("회사 사무실 OL 야근", concepts)
    both = concept_coverage("비 오는 날 사무실에서 시작된 이야기 rainy office", concepts)
    assert only_office == 0.5
    assert both == 1.0
    assert blend_embedding_lexical_score(0.6, only_office, concept_n=2) < blend_embedding_lexical_score(
        0.6, both, concept_n=2
    )


def test_expand_query_concepts_skips_filler_tokens(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("비오는 날 사무실에서 보고싶은 작품")
    flat = {s for group in concepts for s in group}
    assert any("비" in s or "rain" in s for s in flat)
    assert any("사무실" in s or "office" in s for s in flat)
    # 필러는 개념으로 잡히지 않음
    assert "작품" not in flat
    assert "보고싶은" not in flat
    assert len(concepts) == 2


def test_expand_query_concepts_english_office_alias(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("rainy office")
    assert len(concepts) >= 2
    blob = "비 오는 사무실"
    assert concept_coverage(blob, concepts) == 1.0


def test_expand_query_concepts_genre_aliases(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("유부녀 마사지")
    assert len(concepts) == 2
    assert concept_coverage("人妻マッサージオイル", concepts) == 1.0
    assert concept_coverage("普通の話", concepts) == 0.0


def test_expand_query_concepts_merges_live_genres(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {"독점배달": ("독점배달",)},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("독점배달 추천")
    assert len(concepts) == 1
    assert concepts[0] == ["독점배달"]
    assert concept_coverage("오늘 독점배달 신작", concepts) == 1.0


def test_compound_token_resolves_massage_concept(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    concepts = expand_query_concepts("마사지받는장면")
    assert len(concepts) == 1
    assert "마사지" in concepts[0]


def test_is_known_concept_token_short_genre_aliases(monkeypatch):
    monkeypatch.setattr(
        "javstory.library.embeddings.query_format._load_live_genre_concepts",
        lambda: {},
    )
    clear_concept_lexicon_cache()
    assert is_known_concept_token("간호사") is True
    assert is_known_concept_token("메이드") is True
    assert is_known_concept_token("비서") is True
    assert is_known_concept_token("office") is True
    assert is_known_concept_token("미카미") is False
    assert is_known_concept_token("") is False


def test_blend_multi_concept_partial_match_is_gentler_than_floor():
    cosine = 0.6
    none = blend_embedding_lexical_score(cosine, 0.0, concept_n=2)
    half = blend_embedding_lexical_score(cosine, 0.5, concept_n=2)
    full = blend_embedding_lexical_score(cosine, 1.0, concept_n=2)
    assert none == pytest.approx(cosine * 0.55)
    assert half == pytest.approx(cosine * 0.775)
    assert full == pytest.approx(cosine)
    assert none < half < full
