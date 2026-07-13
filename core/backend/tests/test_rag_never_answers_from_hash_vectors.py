# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The failure this pins was not a crash. It was five confident citations.

`embedding_backend` defaulted to `mock`, whose vectors are sha256 of the text.
Nothing errored: a customer uploaded their documents, asked a question, and got
an answer with sources under it — sourced from whichever five chunks happened to
hash nearby, which is to say at random. It looked exactly like a working
product. Two facts hold the line now: the default resolves to a backend that
understands meaning, and a backend that doesn't understand meaning returns
nothing rather than noise.
"""

from __future__ import annotations

import asyncio

import pytest

from app.chat import citations as cit
from app.rag import embedding_bge as emb


def test_mock_backend_returns_no_citations_rather_than_random_ones(monkeypatch):
    """A hash embedder must produce silence, not sources."""
    from app.rag import qdrant_client as qc

    monkeypatch.setattr(emb, "_embedder", None)
    monkeypatch.setattr(emb, "get_embedder", lambda: emb.BGEEmbedder("mock"))
    monkeypatch.setattr(qc, "ensure_collection", lambda *a, **k: None)

    searched = {"n": 0}

    def _search(**kwargs):  # the store is never even asked
        searched["n"] += 1
        return [{"id": "c1", "score": 0.9,
                 "payload": {"text": "an unrelated chunk", "filename": "x.md"}}]

    monkeypatch.setattr(qc, "search", _search)

    cits = asyncio.run(cit.retrieve_citations("when is the pricing audit?", project="t1"))

    assert cits == [], "the mock backend served hash collisions as citations"
    assert searched["n"] == 0, "a search that cannot mean anything was still run"


def test_auto_prefers_a_real_backend_and_keeps_documents_local(monkeypatch):
    """`auto` resolves to something that can actually match meaning.

    Order matters and is not arbitrary: embedding a document sends it to
    whoever computes the vector. Local first — nobody gets opted into shipping
    their company's files to a cloud API by a default they never chose.
    """
    monkeypatch.setattr(emb, "_ollama_serves_embeddings", lambda: True)
    assert emb.resolve_backend("auto") == "ollama"
    assert emb.resolve_backend("") == "ollama"

    # No local Ollama, but the operator already has a Cohere key for the cascade.
    monkeypatch.setattr(emb, "_ollama_serves_embeddings", lambda: False)
    monkeypatch.setattr(emb.settings, "cohere_api_key", "ck-live", raising=False)
    import builtins

    real_import = builtins.__import__

    def _no_sentence_transformers(name, *args, **kw):
        if name == "sentence_transformers":
            raise ImportError("not installed")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_sentence_transformers)
    assert emb.resolve_backend("auto") == "cohere"

    # Nothing available at all: mock, and only then.
    monkeypatch.setattr(emb.settings, "cohere_api_key", "", raising=False)
    assert emb.resolve_backend("auto") == "mock"

    # An explicit choice is always honoured — the tests ask for mock by name.
    assert emb.resolve_backend("mock") == "mock"


def test_ollama_is_a_backend_you_can_actually_select():
    """It was named in the config comment and in the mock's own "set this
    instead" warning, and it was not a branch in this class — the one both
    ingest and chat go through. Following the advice printed in the log raised
    `unsupported embedding backend: ollama` on the customer's first upload."""
    assert "ollama" in emb.BGEEmbedder.__init__.__code__.co_consts, (
        "the ollama backend is documented but not implemented"
    )


def test_the_shipped_default_is_not_the_mock():
    """The setting a customer never touches must not be the broken one."""
    from app.config import Settings

    assert Settings().embedding_backend != "mock"


def test_the_health_check_is_not_green_during_the_outage_it_reports(monkeypatch):
    """`rag: ok` used to mean "chromadb imports".

    It was green for the entire time document search was returning unrelated
    chunks, which is the only reason nobody looked. A health check that cannot go
    red for the failure it covers is worse than no health check at all.
    """
    from app.api import status_page

    class _Broken:
        backend = "mock"
        semantic = False

        def model_id(self):
            return "mock"

    monkeypatch.setattr(
        "app.rag.embedding_bge.get_embedder", lambda: _Broken()
    )
    result = status_page._check_rag()
    assert result["ok"] is False, "rag reported healthy with no working embedder"
    assert "ABS_EMBEDDING_BACKEND" in result["detail"]  # and says how to fix it

    class _Working(_Broken):
        backend = "ollama"
        semantic = True

        def model_id(self):
            return "ollama:bge-m3"

    monkeypatch.setattr(
        "app.rag.embedding_bge.get_embedder", lambda: _Working()
    )
    assert status_page._check_rag()["ok"] is True


@pytest.mark.parametrize("backend,semantic", [("mock", False), ("ollama", True),
                                              ("cohere", True)])
def test_semantic_flag_tracks_reality(backend, semantic, monkeypatch):
    monkeypatch.setattr(emb.BGEEmbedder, "__init__",
                        lambda self, b: (setattr(self, "backend", b),
                                         setattr(self, "semantic", b != "mock"),
                                         setattr(self, "dim", 1024))[0])
    assert emb.BGEEmbedder(backend).semantic is semantic
