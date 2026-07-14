"""RAGAS eval + CI regression check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.observability import ragas_eval as r


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ragas_backend", "mock", raising=False)
    r.close_evaluator()
    yield
    r.close_evaluator()


def test_evaluate_empty_returns_zero_scores() -> None:
    scores = r.RagasEvaluator("mock").evaluate([])
    assert scores.n_samples == 0
    assert scores.faithfulness == 0.0


def test_evaluate_full_match_high_faithfulness() -> None:
    sample = r.EvalSample(
        question="What is ABS?",
        answer="ABS is a self-host AI orchestration platform.",
        contexts=["ABS is a self-host AI orchestration platform built by Automatia."],
        ground_truth="ABS is a self-host AI orchestration platform.",
    )
    scores = r.RagasEvaluator("mock").evaluate([sample])
    assert scores.faithfulness > 0.8
    assert scores.context_precision == 1.0
    assert scores.n_samples == 1


def test_evaluate_no_overlap_low_faithfulness() -> None:
    sample = r.EvalSample(
        question="weather today",
        answer="completely unrelated answer text",
        contexts=["ABS RAG documentation chunk"],
    )
    scores = r.RagasEvaluator("mock").evaluate([sample])
    assert scores.faithfulness < 0.2


def test_regression_check_reports_each_drop() -> None:
    base = r.EvalScores(0.9, 0.9, 0.9, 0.9, 50)
    cur = r.EvalScores(0.8, 0.85, 0.85, 0.7, 50)
    fails = r.regression_check(cur, base, max_drop=0.05)
    assert any("faithfulness" in f for f in fails)
    assert any("context_recall" in f for f in fails)
    assert all("answer_relevance" not in f for f in fails)


def test_regression_check_passes_within_tolerance() -> None:
    base = r.EvalScores(0.9, 0.9, 0.9, 0.9, 50)
    cur = r.EvalScores(0.86, 0.87, 0.88, 0.86, 50)
    assert r.regression_check(cur, base, max_drop=0.05) == []


def test_save_and_load_baseline_round_trip(tmp_path: Path) -> None:
    scores = r.EvalScores(0.91, 0.88, 0.87, 0.85, 100)
    target = tmp_path / "ragas_baseline.json"
    r.save_baseline(target, scores)
    loaded = r.load_baseline(target)
    assert loaded.faithfulness == 0.91
    assert loaded.n_samples == 100


def test_load_baseline_missing_returns_zero() -> None:
    out = r.load_baseline(Path("/tmp/does-not-exist.json"))
    assert out.n_samples == 0


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        r.RagasEvaluator("nope")


def test_singleton_lifecycle() -> None:
    r.close_evaluator()
    a = r.get_evaluator()
    b = r.get_evaluator()
    assert a is b
    r.close_evaluator()
    c = r.get_evaluator()
    assert c is not a
