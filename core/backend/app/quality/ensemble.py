# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-051 — Multi-model ensemble + LLM-as-Judge + Opus baseline check.

The Opus baseline gate enforces "ABS ensemble must score ≥ 0.95 × Opus" on
high-criticality tasks. The Judge defaults to a deterministic mock that
ranks by length+keyword overlap so the suite runs offline; production swaps
in an Anthropic Opus call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "ModelOutput",
    "Verdict",
    "EnsembleResult",
    "OpusBaselineFailure",
    "default_judge",
    "run_ensemble",
]


@dataclass(slots=True)
class ModelOutput:
    model: str
    text: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass(slots=True)
class Verdict:
    score: float  # 0..1
    rationale: str
    chosen_model: str  # propagated from input


@dataclass(slots=True)
class EnsembleResult:
    chosen: ModelOutput
    score: float
    candidates: list[ModelOutput]
    judge_verdicts: list[Verdict] = field(default_factory=list)


class OpusBaselineFailure(RuntimeError):
    """Raised when ABS ensemble score < threshold × Opus baseline."""


def _keyword_overlap(target: str, candidate: str) -> float:
    target_tokens = set(target.lower().split())
    cand_tokens = set(candidate.lower().split())
    if not target_tokens:
        return 0.0
    return len(target_tokens & cand_tokens) / len(target_tokens)


def default_judge(question: str, output: ModelOutput) -> Verdict:
    """Heuristic mock: keyword overlap + length penalty for super-short outputs."""
    base = _keyword_overlap(question, output.text)
    length_factor = 1.0 if len(output.text) >= 80 else 0.6
    score = round(min(1.0, base * length_factor + 0.05), 3)
    return Verdict(score=score, rationale="mock judge", chosen_model=output.model)


def run_ensemble(
    *,
    question: str,
    candidates: list[ModelOutput],
    judge: Callable[[str, ModelOutput], Verdict] | None = None,
    opus_baseline: float | None = None,
    opus_threshold: float = 0.95,
) -> EnsembleResult:
    if not candidates:
        raise ValueError("at least one candidate required")
    judge = judge or default_judge
    verdicts = [judge(question, c) for c in candidates]
    paired = sorted(zip(verdicts, candidates), key=lambda pair: -pair[0].score)
    best_verdict, best_candidate = paired[0]
    if opus_baseline is not None:
        floor = opus_threshold * opus_baseline
        if best_verdict.score < floor:
            raise OpusBaselineFailure(
                f"ensemble best {best_verdict.score:.3f} < {floor:.3f} "
                f"({opus_threshold:.0%} of Opus {opus_baseline:.3f})"
            )
    logger.info(
        "ensemble_picked model=%s score=%.3f from=%d",
        best_candidate.model,
        best_verdict.score,
        len(candidates),
    )
    return EnsembleResult(
        chosen=best_candidate,
        score=best_verdict.score,
        candidates=candidates,
        judge_verdicts=verdicts,
    )
