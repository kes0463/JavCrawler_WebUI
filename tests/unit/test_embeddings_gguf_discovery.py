from __future__ import annotations

from pathlib import Path

from javstory.llm import llamacpp_embeddings as emb


def test_discover_embeddings_gguf_prefers_e5_and_bge(monkeypatch, tmp_path):
    (tmp_path / "Qwen3-14B-Q4_K_M.gguf").write_bytes(b"x")
    (tmp_path / "e5-mistral-7b-instruct-Q4_K_M.gguf").write_bytes(b"x")
    (tmp_path / "bge-m3-Q8_0.gguf").write_bytes(b"x")

    monkeypatch.setattr(emb, "embeddings_gguf_scan_dirs", lambda: [tmp_path])

    found = emb.discover_embeddings_gguf_models()
    labels = [o["label"] for o in found]

    assert "e5-mistral-7b-instruct-Q4_K_M.gguf" in labels
    assert "bge-m3-Q8_0.gguf" in labels
    assert "Qwen3-14B-Q4_K_M.gguf" not in labels


def test_list_embeddings_gguf_options_includes_model_hint_first(monkeypatch, tmp_path):
    gguf = tmp_path / "e5-mistral-7b-instruct-Q4_K_M.gguf"
    gguf.write_bytes(b"x")
    monkeypatch.setattr(emb, "embeddings_gguf_scan_dirs", lambda: [tmp_path])
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", "e5-mistral-7b-instruct-Q4_K_M")
    monkeypatch.delenv("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", raising=False)

    opts = emb.list_embeddings_gguf_options()
    assert opts[0]["id"] == ""
    assert opts[1]["label"] == "e5-mistral-7b-instruct-Q4_K_M.gguf"


def test_resolve_embed_gguf_finds_e5_when_env_empty(monkeypatch, tmp_path):
    gguf = tmp_path / "e5-mistral-7b-instruct-Q4_K_M.gguf"
    gguf.write_bytes(b"x")
    monkeypatch.setattr(emb, "embeddings_gguf_scan_dirs", lambda: [tmp_path])
    monkeypatch.delenv("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", raising=False)
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", "e5-mistral-7b-instruct-Q4_K_M")

    resolved = emb._resolve_embed_gguf()
    assert resolved == gguf.resolve()
