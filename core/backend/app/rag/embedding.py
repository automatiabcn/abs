# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Ollama nomic-embed-text wrapper.

Single entry point for embedding so tests can monkeypatch it. Raises
``RuntimeError`` when Ollama is unreachable; callers count ok/fail.
"""

from __future__ import annotations

from typing import List

import httpx

from app.config import settings

_DEFAULT_URL = "http://localhost:11434"


def _base_url() -> str:
    return (settings.ollama_url or _DEFAULT_URL).rstrip("/")


def _model() -> str:
    # Configurable so a deployment can run bge-m3 (1024-dim, multilingual)
    # instead of the nomic-embed-text default.
    return getattr(settings, "embedding_model", "") or "nomic-embed-text"


async def embed(text: str, *, timeout: float = 15.0) -> List[float]:
    """Embed a single text. The backend is chosen by ``ABS_EMBEDDING_BACKEND``.

    Only ``backend == "ollama"`` talks to Ollama. The default (``mock``) and the
    ``sentence_transformers`` / ``onnx`` backends go to the BGE embedder so a
    first boot needs no external service. That embedder is sync and CPU-bound,
    hence the thread offload.
    """
    backend = (getattr(settings, "embedding_backend", "mock") or "mock").lower()
    if backend != "ollama":
        import asyncio

        from app.rag.embedding_bge import get_embedder

        return await asyncio.to_thread(get_embedder().embed_one, text)

    url = f"{_base_url()}/api/embeddings"
    body = {"model": _model(), "prompt": text[:8000]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama embed connection failed: {exc}") from exc
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama embed {r.status_code}: {r.text[:200]}")
    data = r.json()
    vec = data.get("embedding") or []
    if not vec:
        raise RuntimeError("Ollama embed: empty vector")
    return list(vec)
