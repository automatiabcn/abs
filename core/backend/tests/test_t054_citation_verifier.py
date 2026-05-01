"""T-054 — Citation verifier tests."""

from __future__ import annotations

import pytest

from app.quality.verifiers.citation import verify_citations


def test_supported_claims_get_high_score() -> None:
    rep = verify_citations(
        answer="ABS RAG runs on Qdrant. Cerbos enforces tenant isolation.",
        contexts=[
            "ABS RAG pipeline runs on Qdrant payload-filter.",
            "Cerbos pre-filter enforces tenant isolation before Qdrant.",
        ],
    )
    assert rep.score == 1.0
    assert rep.orphan_claims == []
    assert all(m.best_context_index is not None for m in rep.matches)


def test_orphan_claim_detected() -> None:
    rep = verify_citations(
        answer="ABS RAG uses BGE-M3. Mars colonisation is imminent.",
        contexts=["ABS RAG uses BGE-M3 embedding."],
    )
    assert rep.score == 0.5
    assert any("Mars" in c for c in rep.orphan_claims)


def test_unused_context_reported() -> None:
    rep = verify_citations(
        answer="abs rag uses qdrant.",
        contexts=[
            "abs rag uses qdrant payload-filter",
            "globex roadmap mentions paris launch",
        ],
    )
    assert rep.unused_contexts == [1]


def test_empty_answer_returns_perfect_score() -> None:
    rep = verify_citations(answer="", contexts=["any context"])
    assert rep.score == 1.0
    assert rep.matches == []


def test_threshold_validation() -> None:
    with pytest.raises(ValueError):
        verify_citations(answer="x.", contexts=["x"], threshold=2.0)


def test_lower_threshold_rescues_weak_matches() -> None:
    rep = verify_citations(
        answer="ABS RAG short.",
        contexts=["ABS"],
        threshold=0.05,
    )
    assert rep.score >= 1.0 - 1e-9
