# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-054 — Citation verifier (REFCHECKER lite).

Splits an answer into claim sentences, finds the strongest matching context for
each, and reports orphan claims (no support) + unused contexts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "ClaimMatch",
    "CitationReport",
    "verify_citations",
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s]", "", text.lower()).split())


@dataclass(slots=True)
class ClaimMatch:
    claim: str
    best_context_index: int | None
    score: float


@dataclass(slots=True)
class CitationReport:
    matches: list[ClaimMatch]
    orphan_claims: list[str]
    unused_contexts: list[int]
    score: float  # 0..1 = supported claims ratio


def verify_citations(
    *,
    answer: str,
    contexts: list[str],
    threshold: float = 0.3,
) -> CitationReport:
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be in [0, 1]")
    claims = _sentences(answer)
    if not claims:
        return CitationReport(
            matches=[], orphan_claims=[], unused_contexts=[], score=1.0
        )

    ctx_tokens = [_tokens(c) for c in contexts]
    matches: list[ClaimMatch] = []
    used: set[int] = set()
    for claim in claims:
        ct = _tokens(claim)
        best = (None, 0.0)
        for idx, tokens in enumerate(ctx_tokens):
            if not ct or not tokens:
                continue
            score = len(ct & tokens) / len(ct)
            if score > best[1]:
                best = (idx, score)
        matches.append(
            ClaimMatch(
                claim=claim,
                best_context_index=best[0] if best[1] >= threshold else None,
                score=best[1],
            )
        )
        if best[0] is not None and best[1] >= threshold:
            used.add(best[0])

    supported = [m for m in matches if m.best_context_index is not None]
    orphans = [m.claim for m in matches if m.best_context_index is None]
    unused = sorted(set(range(len(contexts))) - used)
    score = len(supported) / len(matches) if matches else 1.0
    return CitationReport(
        matches=matches,
        orphan_claims=orphans,
        unused_contexts=unused,
        score=score,
    )
