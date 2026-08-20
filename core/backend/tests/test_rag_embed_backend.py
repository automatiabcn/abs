# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""embedding.embed() honours ABS_EMBEDDING_BACKEND.

Two contracts, and both have to be proven against a fresh embedder — the
singleton in `embedding_bge` is built once per process, so a test that flips
`settings.embedding_backend` without resetting it is asserting against whatever
an earlier test happened to construct (on CI that was the real
sentence-transformers backend, 384-dim, and these tests failed for it).

1. `mock`, asked for by name, never touches Ollama and is deterministic.
2. An UNSET backend never resolves to `mock`. It used to — that was the
   "chat with your documents answered from the wrong documents" bug — so the
   resolver now picks a real backend the box can run, or `none`, and `none`
   refuses to embed rather than returning a meaningless vector.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fresh_embedder(monkeypatch):
    """Drop the process-wide embedder so `settings` changes take effect, and put
    whatever was there back afterwards for the tests that run next."""
    from app.rag import embedding_bge

    monkeypatch.setattr(embedding_bge, "_embedder", None)
    yield embedding_bge


@pytest.mark.asyncio
async def test_embed_mock_backend_no_ollama(monkeypatch, fresh_embedder):
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_backend", "mock")
    # Point Ollama at a dead address; if embed() wrongly hit Ollama it would
    # raise. With backend=mock it must use the local mock embedder instead.
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:1", raising=False)

    from app.rag import embedding

    vec = await embedding.embed("RAG mock backend regression text")
    assert isinstance(vec, list) and len(vec) == 1024  # mock dim, not 768 nomic
    # deterministic
    vec2 = await embedding.embed("RAG mock backend regression text")
    assert vec == vec2
    assert fresh_embedder.get_embedder().backend == "mock"
    assert fresh_embedder.get_embedder().semantic is False


@pytest.mark.asyncio
async def test_embed_unset_backend_never_resolves_to_mock(monkeypatch, fresh_embedder):
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_backend", "", raising=False)
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:1", raising=False)

    from app.rag import embedding

    embedder = fresh_embedder.get_embedder()
    assert embedder.backend != "mock", "an unset backend silently became mock again"

    if embedder.backend == "none":
        # Nothing real to run on this box: the honest answer is a refusal.
        with pytest.raises(fresh_embedder.EmbeddingUnavailable):
            await embedding.embed("unset backend with no real embedder")
    else:
        # A real backend was found (Ollama, sentence-transformers, Cohere):
        # it must understand meaning, and it must answer.
        assert embedder.semantic is True
        vec = await embedding.embed("unset backend resolves to a real embedder")
        assert isinstance(vec, list) and len(vec) == embedder.dim > 0
