from __future__ import annotations


def test_build_focused_context_selects_relevant_items(monkeypatch):
    from javstory.persona import erotic_persona_engine as engine

    def fake_embed_texts(texts):
        vectors = []
        for text in texts:
            if "마사지" in text:
                vectors.append([1.0, 0.0])
            elif "코미디" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.2, 0.0])
        return vectors

    monkeypatch.setattr(engine, "_embed_texts_blocking", fake_embed_texts)

    focused = engine.build_focused_context(
        "마사지 분위기 추천",
        {
            "turn_ons": ["마사지", "긴장감"],
            "avoidances": ["코미디"],
            "summary": "마사지 관계성 취향",
        },
    )

    assert focused.startswith("[취향 정보]")
    assert "turn_ons" in focused
    assert "summary" in focused
    assert "avoidances" not in focused


def test_build_focused_context_returns_header_on_embedding_failure(monkeypatch):
    from javstory.persona import erotic_persona_engine as engine

    def fail_embed(_texts):
        raise RuntimeError("offline")

    monkeypatch.setattr(engine, "_embed_texts_blocking", fail_embed)

    assert engine.build_focused_context("마사지", {"turn_ons": ["마사지"]}) == "[취향 정보]"
