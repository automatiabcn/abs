# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A server with no reranker does not rerank.

`rerank_backend` defaulted to `mock`: Jaccard word overlap, on a request whose API
field is documented as `apply T-013 cross-encoder rerank`. It is not a weaker
cross-encoder — it is a different and worse ranking function, promoting chunks that
repeat the query's words over chunks that answer the question. Measured on the golden
set it ranked below not reranking at all, which is the whole story: the feature made
retrieval worse and reported itself as working.

Same shape as the embedding bug, same fix — `auto` resolves to what the server can
actually do, and the fallback is honest emptiness rather than a plausible imitation.
"""

from __future__ import annotations

from app.config import Settings, settings
from app.rag.reranker import Reranker, resolve_rerank_backend


def test_the_default_is_auto_not_a_pretend_cross_encoder():
    assert Settings().rerank_backend == "auto"


def test_auto_on_a_bare_server_means_no_reranking(monkeypatch):
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    monkeypatch.setattr(settings, "rerank_model_path", "", raising=False)

    assert resolve_rerank_backend("auto") == "none"


def test_auto_finds_cohere_when_a_key_is_there(monkeypatch):
    monkeypatch.setattr(settings, "cohere_api_key", "co-key", raising=False)
    monkeypatch.setattr(settings, "rerank_model_path", "", raising=False)

    assert resolve_rerank_backend("auto") == "cohere"


def test_auto_finds_the_local_cross_encoder_when_one_is_installed(monkeypatch):
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    monkeypatch.setattr(settings, "rerank_model_path", "/models/qwen3.onnx", raising=False)

    assert resolve_rerank_backend("auto") == "qwen3_onnx"


def test_no_reranker_leaves_the_dense_order_exactly_as_it_was(monkeypatch):
    """Not "roughly". Exactly. The dense order is the retrieval system's answer,
    and with nothing to improve on it, nothing may disturb it."""
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    monkeypatch.setattr(settings, "rerank_model_path", "", raising=False)

    docs = [
        "the pension scheme changed in April",
        "query query query query",          # the mock would have hoisted this
        "annual leave carries over",
    ]
    out = Reranker("auto").rerank("query", docs, top_k=3)

    assert [r.index for r in out] == [0, 1, 2]
    assert [r.doc for r in out] == docs


def test_the_word_overlap_backend_would_have_reordered_it(monkeypatch):
    """The counterfactual, so the previous test is not a tautology: the old default
    really does move the word-stuffed chunk to the top of a customer's answer."""
    out = Reranker("mock").rerank(
        "query",
        [
            "the pension scheme changed in April",
            "query query query query",
            "annual leave carries over",
        ],
        top_k=3,
    )

    assert out[0].index == 1
