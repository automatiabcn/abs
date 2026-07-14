"""Multi-model ensemble + Opus baseline tests."""

from __future__ import annotations

import pytest

from app.quality.ensemble import (
    ModelOutput,
    OpusBaselineFailure,
    default_judge,
    run_ensemble,
)


def test_default_judge_scores_within_zero_one() -> None:
    out = ModelOutput(model="kimi", text="ABS RAG embedding pipeline " * 4)
    v = default_judge("ABS RAG embedding pipeline", out)
    assert 0.0 <= v.score <= 1.0


def test_run_ensemble_picks_highest_scoring() -> None:
    cands = [
        ModelOutput(model="kimi", text="abs rag detail" * 6),
        ModelOutput(model="opus", text="abs rag detailed answer extending well " * 4),
    ]
    res = run_ensemble(question="abs rag detailed", candidates=cands)
    assert res.chosen.model == "opus"
    assert len(res.judge_verdicts) == 2


def test_run_ensemble_requires_candidate() -> None:
    with pytest.raises(ValueError):
        run_ensemble(question="x", candidates=[])


def test_opus_baseline_failure_when_below_threshold() -> None:
    cands = [ModelOutput(model="kimi", text="short")]
    with pytest.raises(OpusBaselineFailure):
        run_ensemble(
            question="long detailed multi-paragraph answer about ABS RAG",
            candidates=cands,
            opus_baseline=0.95,
            opus_threshold=0.95,
        )


def test_opus_baseline_pass_when_at_floor() -> None:
    long_text = "abs rag pipeline detailed answer " * 5
    cands = [ModelOutput(model="opus", text=long_text)]
    res = run_ensemble(
        question="abs rag pipeline detailed answer",
        candidates=cands,
        opus_baseline=0.5,
        opus_threshold=0.5,
    )
    assert res.chosen.model == "opus"


def test_judge_can_be_overridden() -> None:
    def stub_judge(q, c):  # noqa: ANN001
        return type(
            "V",
            (),
            {
                "score": 0.7 if c.model == "groq" else 0.1,
                "rationale": "stub",
                "chosen_model": c.model,
            },
        )()

    res = run_ensemble(
        question="hello",
        candidates=[
            ModelOutput(model="kimi", text="x"),
            ModelOutput(model="groq", text="y"),
        ],
        judge=stub_judge,
    )
    assert res.chosen.model == "groq"
    assert res.score == 0.7
