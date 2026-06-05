# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""RAG round — real semantic embeddings via the customer's Cohere key (BYOK).

Makes RAG actually work out of the box without the mock embedder, ollama, or a
2 GB sentence-transformers download: ABS_EMBEDDING_BACKEND=cohere reuses the key
the customer already configured for the model cascade. embed-multilingual-v3.0
is 1024-dim, matching qdrant_default_vector_size — no collection migration.
"""
from __future__ import annotations

import sys
import types

import pytest

from app.config import settings
from app.rag import embedding_bge as eb


def test_cohere_backend_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    with pytest.raises(ValueError, match="ABS_COHERE_API_KEY"):
        eb._CohereBackend()


def _install_fake_cohere(monkeypatch, captured: dict):
    """Inject a fake `cohere` module whose AsyncClientV2.embed records args and
    returns deterministic 1024-dim float vectors."""

    class _Emb:
        def __init__(self, vecs):
            self.float = vecs

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def embed(self, *, texts, model, input_type, embedding_types):
            captured["model"] = model
            captured["input_type"] = input_type
            captured["n"] = len(texts)
            return types.SimpleNamespace(
                embeddings=_Emb([[0.01 * (j % 7) for j in range(1024)] for _ in texts])
            )

    fake = types.ModuleType("cohere")
    fake.AsyncClientV2 = _FakeClient
    monkeypatch.setitem(sys.modules, "cohere", fake)


def test_cohere_backend_embeds_1024_dim(monkeypatch):
    monkeypatch.setattr(settings, "cohere_api_key", "co-test-key", raising=False)
    captured: dict = {}
    _install_fake_cohere(monkeypatch, captured)

    emb = eb.BGEEmbedder("cohere")
    assert emb.dim == 1024
    vecs = emb.embed(["hello world", "second chunk"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)
    assert captured["model"] == "embed-multilingual-v3.0"
    assert captured["input_type"] == "search_document"

    one = emb.embed_one("a query")
    assert len(one) == 1024
