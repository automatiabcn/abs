"""T-052 — Hallucination guard tests."""

from __future__ import annotations

import pytest

from app.quality.hallucination_guard import (
    HallucinationGuard,
    estimate_faithfulness,
)


def test_estimate_faithfulness_full_overlap() -> None:
    score = estimate_faithfulness(
        answer="abs rag pipeline",
        contexts=["abs rag pipeline production"],
    )
    assert score == 1.0


def test_estimate_faithfulness_no_overlap() -> None:
    score = estimate_faithfulness(
        answer="cosmology paper",
        contexts=["abs rag pipeline"],
    )
    assert score == 0.0


def test_guard_passes_when_above_threshold() -> None:
    guard = HallucinationGuard(threshold=0.5, max_revisions=2)
    res = guard.enforce(
        answer="abs rag",
        contexts=["abs rag detailed"],
        revise_fn=lambda a, c: a,
    )
    assert res.faithfulness >= 0.5
    assert res.revision_count == 0


def test_guard_revises_until_threshold() -> None:
    guard = HallucinationGuard(threshold=0.6, max_revisions=2)

    def revise(a, contexts):  # noqa: ANN001
        return "abs rag pipeline production"

    res = guard.enforce(
        answer="totally unrelated",
        contexts=["abs rag pipeline production"],
        revise_fn=revise,
    )
    assert res.faithfulness >= 0.6
    assert res.revision_count >= 1


def test_guard_exhausts_revisions() -> None:
    guard = HallucinationGuard(threshold=0.99, max_revisions=2)
    res = guard.enforce(
        answer="x",
        contexts=["y"],
        revise_fn=lambda a, c: "z",
    )
    assert res.revision_count == 2
    assert "exhausted" in res.audit[-1]


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError):
        HallucinationGuard(threshold=0.0)
    with pytest.raises(ValueError):
        HallucinationGuard(threshold=1.5)
