# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Disagreement detector — ask N providers in parallel, measure how far apart
their answers are.

Similarity comes from Cohere embeddings when Cohere is configured, and from a
character-level Jaccard overlap when it is not: crude, but it needs no provider
of its own, so the detector never goes blind just because embeddings are down.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from app.pipelines.execution import run_parallel_named
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

# Three models from different families — agreement between siblings proves little.
DEFAULT_MODELS: List[Tuple[str, str, str]] = [
    ("groq-gptoss", "groq", "openai/gpt-oss-120b"),
    ("cf-kimi", "cloudflare", "@cf/moonshotai/kimi-k2.5"),
    ("cerebras", "cerebras", "gpt-oss-120b"),
]


def _jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"\w+", a.lower()))
    tb = set(re.findall(r"\w+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def ask_disagree(prompt: str, analyzer_model: str | None = None) -> Dict:
    """Ask the providers in parallel, build a similarity matrix, score the consensus."""
    coros = {
        name: get_provider(prov).call(prompt, model=mdl)
        for name, prov, mdl in DEFAULT_MODELS
    }
    raw = await run_parallel_named(coros)

    responses: Dict[str, str] = {}
    for name, r in raw.items():
        if isinstance(r, BaseException):
            responses[name] = ""
        else:
            responses[name] = getattr(r, "text", "") or ""

    ok_names = [n for n, t in responses.items() if t]

    # Cosine over Cohere embeddings, else the Jaccard fallback
    sim_matrix: List[List[float]] = []
    try:
        cohere = get_provider("cohere")
        if not hasattr(cohere, "embed"):
            raise AttributeError("no embed")
        embeds: Dict[str, List[float]] = {}
        for n in ok_names:
            try:
                embeds[n] = await cohere.embed(responses[n])  # type: ignore[attr-defined]
            except Exception:
                embeds[n] = []
        if all(embeds.get(n) for n in ok_names):
            for a in ok_names:
                row = [_cosine(embeds[a], embeds[b]) for b in ok_names]
                sim_matrix.append(row)
    except Exception:
        pass

    if not sim_matrix and len(ok_names) > 1:
        # Jaccard fallback
        for a in ok_names:
            row = [_jaccard(responses[a], responses[b]) for b in ok_names]
            sim_matrix.append(row)

    # Consensus: the mean of the off-diagonal pairs
    consensus = None
    if sim_matrix and len(sim_matrix) > 1:
        off = [
            sim_matrix[i][j]
            for i in range(len(sim_matrix))
            for j in range(len(sim_matrix))
            if i != j
        ]
        consensus = sum(off) / max(1, len(off))

    level = "none"
    if consensus is not None:
        if consensus >= 0.8:
            level = "high"
        elif consensus >= 0.5:
            level = "medium"
        else:
            level = "low"

    return {
        "status": "ok" if ok_names else "empty",
        "models": ok_names,
        "responses": {n: responses[n][:600] for n in ok_names},
        "similarity_matrix": sim_matrix,
        "consensus_score": round(consensus, 3) if consensus is not None else None,
        "consensus_level": level,
        "note": "Cohere embed yoksa Jaccard fallback.",
    }
