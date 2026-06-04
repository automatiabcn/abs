# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""embedding.embed() honours ABS_EMBEDDING_BACKEND — the default 'mock' must
NOT require Ollama (regression for the RAG-broken-on-default finding)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_embed_mock_backend_no_ollama(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_backend", "mock")
    # Point Ollama at a dead address; if embed() wrongly hit Ollama it would
    # raise. With backend=mock it must use the local BGE mock embedder instead.
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:1", raising=False)

    from app.rag import embedding

    vec = await embedding.embed("RAG mock backend regression text")
    assert isinstance(vec, list) and len(vec) == 1024  # mock dim, not 768 nomic
    # deterministic
    vec2 = await embedding.embed("RAG mock backend regression text")
    assert vec == vec2


@pytest.mark.asyncio
async def test_embed_unset_backend_defaults_mock(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_backend", "", raising=False)
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:1", raising=False)

    from app.rag import embedding

    vec = await embedding.embed("unset backend defaults to mock")
    assert len(vec) == 1024  # falls back to mock, not Ollama
