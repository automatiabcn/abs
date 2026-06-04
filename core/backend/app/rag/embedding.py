# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Ollama nomic-embed-text wrapper.

Test ortamında `monkeypatch` ile fake embed döndürebilmek için tek noktadan
çağrılır. Ollama erişilemezse `RuntimeError` yükselir; üst katman 'ok'/'fail'
sayısı raporlar.
"""

from __future__ import annotations

import json
from typing import List

import httpx

from app.config import settings

_DEFAULT_URL = "http://localhost:11434"
_MODEL = "nomic-embed-text"


def _base_url() -> str:
    return (settings.ollama_url or _DEFAULT_URL).rstrip("/")


async def embed(text: str, *, timeout: float = 15.0) -> List[float]:
    """Tek metin için embedding. Backend ``ABS_EMBEDDING_BACKEND`` ile seçilir.

    Müşteri compose default'u ``mock`` (sha256-türevli, $0, Ollama gerektirmez)
    — "zero-dep first boot" sözünün gereği. Pre-fix bu fonksiyon her zaman
    Ollama nomic'e gidiyordu, dolayısıyla mock/bge backend'lerde RAG index+query
    "Ollama embed bağlantı: All connection attempts failed" ile patlıyordu.
    Artık yalnızca ``backend == "ollama"`` Ollama'ya gider; mock /
    sentence_transformers / onnx, backend-aware BGE embedder'a delege edilir
    (sync + CPU-bound olduğu için thread'de).
    """
    backend = (getattr(settings, "embedding_backend", "mock") or "mock").lower()
    if backend != "ollama":
        import asyncio

        from app.rag.embedding_bge import get_embedder

        return await asyncio.to_thread(get_embedder().embed_one, text)

    url = f"{_base_url()}/api/embeddings"
    body = {"model": _MODEL, "prompt": text[:8000]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama embed bağlantı: {exc}") from exc
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama embed {r.status_code}: {r.text[:200]}")
    data = r.json()
    vec = data.get("embedding") or []
    if not vec:
        raise RuntimeError("Ollama embed: boş vektör")
    return list(vec)
