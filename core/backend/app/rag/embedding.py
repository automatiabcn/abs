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
    """Tek metin için embedding (768-dim nomic). Liste boşsa Ollama down."""
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
