"""
Ollama embeddings helper.

- Uses native Ollama endpoint: POST {OLLAMA_BASE_URL}/api/embeddings
  (Not the OpenAI-compatible /v1/embeddings, to avoid server/version differences.)
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from javstory.config.app_config import OLLAMA_BASE_URL


async def ollama_embed_text(
    *,
    text: str,
    model: str,
    base_url: str = OLLAMA_BASE_URL,
    timeout_sec: float = 300.0,
) -> List[float]:
    """
    Return an embedding vector for `text`.

    Raises on HTTP errors or missing embedding.
    """
    t = (text or "").strip()
    if not t:
        raise ValueError("ollama_embed_text: text is empty")
    m = (model or "").strip()
    if not m:
        raise ValueError("ollama_embed_text: model is empty")

    url = f"{base_url.rstrip('/')}/api/embeddings"
    payload: Dict[str, Any] = {"model": m, "prompt": t}

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec, connect=5.0)) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()

    emb = data.get("embedding")
    if not isinstance(emb, list) or not emb:
        raise ValueError("ollama_embed_text: embedding missing in response")
    try:
        return [float(x) for x in emb]
    except Exception as e:
        raise ValueError(f"ollama_embed_text: embedding is not numeric: {e}")


async def ollama_embed_texts(
    *,
    texts: List[str],
    model: str,
    base_url: str = OLLAMA_BASE_URL,
    timeout_sec: float = 300.0,
) -> List[List[float]]:
    """
    Embed multiple texts sequentially.
    (Ollama's embedding endpoint is typically fast; keep it simple and predictable.)
    """
    out: List[List[float]] = []
    for t in texts:
        out.append(
            await ollama_embed_text(
                text=t,
                model=model,
                base_url=base_url,
                timeout_sec=timeout_sec,
            )
        )
    return out

