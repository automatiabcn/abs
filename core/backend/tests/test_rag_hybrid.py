"""016 — RAG hybrid (BM25 + cosine fusion) testleri."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest


def test_tokenize_basic():
    from app.rag.hybrid import _tokenize

    assert _tokenize("Hello, World!") == ["hello", "world"]
    assert _tokenize("foo_bar baz123") == ["foo_bar", "baz123"]
    assert _tokenize("") == []


def test_bm25_higher_for_keyword_match():
    from app.rag.hybrid import _bm25_score, _tokenize

    docs = ["circuit breaker pattern", "random unrelated content"]
    tokenized = [_tokenize(d) for d in docs]
    n = len(docs)
    avg_dl = sum(len(t) for t in tokenized) / max(n, 1)
    doc_freqs: Dict[str, int] = {}
    for toks in tokenized:
        for tok in set(toks):
            doc_freqs[tok] = doc_freqs.get(tok, 0) + 1
    q = _tokenize("circuit breaker")
    s_match = _bm25_score(q, tokenized[0], avg_dl, doc_freqs, n)
    s_other = _bm25_score(q, tokenized[1], avg_dl, doc_freqs, n)
    assert s_match > s_other
    assert s_match > 0
    assert s_other == 0


def test_normalize_min_max():
    from app.rag.hybrid import _normalize

    assert _normalize([]) == []
    assert _normalize([1.0, 1.0, 1.0]) == [0.0, 0.0, 0.0]
    out = _normalize([1.0, 3.0, 5.0])
    assert out == [0.0, 0.5, 1.0]


@pytest.mark.asyncio
async def test_query_hybrid_empty_question():
    from app.rag.hybrid import query_hybrid

    assert await query_hybrid("") == []
    assert await query_hybrid("   ") == []


@pytest.mark.asyncio
async def test_query_hybrid_uses_both_signals(monkeypatch):
    """Mock embedding + chroma collection — BM25 ile cosine fusion doğru sırada."""
    from app.rag import embedding as emb_mod
    from app.rag import hybrid as hybrid_mod

    async def fake_embed(text):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(emb_mod, "embed", fake_embed)

    class FakeCollection:
        def query(self, query_embeddings, n_results, where=None):
            return {
                "documents": [
                    [
                        "circuit breaker pattern with retry",
                        "totally unrelated text about cats",
                        "circuit breaker resilience cascade",
                    ]
                ],
                "metadatas": [
                    [
                        {"file": "a.py", "project": "p1"},
                        {"file": "b.py", "project": "p1"},
                        {"file": "c.py", "project": "p1"},
                    ]
                ],
                "distances": [[0.1, 0.5, 0.3]],
            }

    monkeypatch.setattr(hybrid_mod, "_collection", lambda: FakeCollection())

    res = await hybrid_mod.query_hybrid(
        "circuit breaker", top_k=3, alpha_semantic=0.6
    )
    assert isinstance(res, list)
    assert len(res) == 3
    # circuit breaker keyword içeren ilk sırada
    assert "circuit breaker" in res[0]["snippet"]
    # her entry expected fields
    for item in res:
        assert "score" in item
        assert "bm25" in item
        assert "cosine" in item


@pytest.mark.asyncio
async def test_alpha_zero_pure_bm25(monkeypatch):
    """alpha_semantic=0 → sadece BM25 — keyword match en üstte olmalı."""
    from app.rag import embedding as emb_mod
    from app.rag import hybrid as hybrid_mod

    async def fake_embed(text):
        return [0.1, 0.2]

    monkeypatch.setattr(emb_mod, "embed", fake_embed)

    class FakeCollection:
        def query(self, query_embeddings, n_results, where=None):
            return {
                "documents": [
                    [
                        "no keyword here at all",  # cosine high (low dist), no keyword
                        "the special_token target appears",  # cosine low, keyword match
                    ]
                ],
                "metadatas": [[{"file": "x.py"}, {"file": "y.py"}]],
                "distances": [[0.05, 0.9]],  # ilk doc cosine'ı yüksek
            }

    monkeypatch.setattr(hybrid_mod, "_collection", lambda: FakeCollection())

    res = await hybrid_mod.query_hybrid(
        "special_token", top_k=2, alpha_semantic=0.0
    )
    # alpha=0 → keyword match (y.py) ilk sırada
    assert res[0]["file"] == "y.py"
    assert res[1]["file"] == "x.py"
