# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""RAG round — the mock embedder must LOUDLY warn that semantic search is off.

The customer compose defaults ABS_EMBEDDING_BACKEND=mock for a zero-dependency
first boot, but mock vectors are sha256-derived: RAG only matches byte-identical
text, so semantic retrieval is non-functional. Previously this was a quiet INFO
line that read like normal startup. It must be a WARNING so operators know RAG
search won't actually work until they configure a real backend.
"""
from __future__ import annotations

import logging

from app.rag.embedding_bge import BGEEmbedder, _MockBackend


def test_mock_backend_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.rag.embedding_bge"):
        _MockBackend(dim=8)
    msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("NON-FUNCTIONAL" in m for m in msgs), msgs
    assert any("ABS_EMBEDDING_BACKEND" in m for m in msgs), msgs


def test_mock_embedder_only_matches_identical_text():
    """Demonstrates WHY mock is non-semantic: identical text → cosine 1.0,
    different-but-related text → near-orthogonal (proves the warning is true)."""
    emb = BGEEmbedder("mock")
    a = emb.embed_one("reset my password")
    a2 = emb.embed_one("reset my password")
    b = emb.embed_one("how do I recover account access")

    def _cos(x, y):
        return sum(i * j for i, j in zip(x, y))

    assert _cos(a, a2) > 0.999  # identical text matches
    # Semantically related but textually different → not meaningfully similar.
    assert _cos(a, b) < 0.5
