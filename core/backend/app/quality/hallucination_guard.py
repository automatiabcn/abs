# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-052 — Hallucination guard. faithfulness < 0.85 → mandatory revise."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "GuardResult",
    "HallucinationGuard",
    "estimate_faithfulness",
]


def estimate_faithfulness(*, answer: str, contexts: list[str]) -> float:
    if not answer:
        return 0.0
    answer_tokens = set(answer.lower().split())
    if not answer_tokens:
        return 0.0
    ctx_tokens: set[str] = set()
    for c in contexts:
        ctx_tokens.update(c.lower().split())
    if not ctx_tokens:
        return 0.0
    return len(answer_tokens & ctx_tokens) / len(answer_tokens)


@dataclass(slots=True)
class GuardResult:
    answer: str
    faithfulness: float
    revision_count: int
    audit: list[str]


class HallucinationGuard:
    def __init__(
        self,
        *,
        threshold: float = 0.85,
        max_revisions: int = 3,
        scorer: Callable[..., float] | None = None,
    ) -> None:
        if not (0.0 < threshold <= 1.0):
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold
        self.max_revisions = max_revisions
        self._scorer = scorer or (lambda **kw: estimate_faithfulness(**kw))

    def enforce(
        self,
        *,
        answer: str,
        contexts: list[str],
        revise_fn: Callable[[str, list[str]], str],
    ) -> GuardResult:
        audit: list[str] = []
        current = answer
        for attempt in range(self.max_revisions + 1):
            score = self._scorer(answer=current, contexts=contexts)
            audit.append(f"attempt={attempt} score={score:.3f}")
            if score >= self.threshold:
                logger.info(
                    "hallucination_guard_pass attempts=%d score=%.3f",
                    attempt,
                    score,
                )
                return GuardResult(
                    answer=current,
                    faithfulness=score,
                    revision_count=attempt,
                    audit=audit,
                )
            if attempt == self.max_revisions:
                logger.warning(
                    "hallucination_guard_exhausted score=%.3f", score
                )
                return GuardResult(
                    answer=current,
                    faithfulness=score,
                    revision_count=attempt,
                    audit=audit + ["exhausted"],
                )
            current = revise_fn(current, contexts)
        return GuardResult(
            answer=current,
            faithfulness=0.0,
            revision_count=self.max_revisions,
            audit=audit,
        )
