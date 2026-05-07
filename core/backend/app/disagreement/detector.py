# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Disagreement detector — N provider paralel + cosine similarity.

Embedding için: Cohere varsa `CohereProvider.embed`, yoksa character-level Jaccard
fallback (dumb ama bağımsız). Consensus eşikleri SERVER ile paralel.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from app.pipelines.execution import run_parallel_named
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

# Varsayılan 3 model — farklı aileler (çeşitlilik)
DEFAULT_MODELS: List[Tuple[str, str, str]] = [
    ("groq-gptoss", "groq", "openai/gpt-oss-120b"),
    ("cf-kimi", "cloudflare", "@cf/moonshotai/kimi-k2.5"),
    ("cerebras", "cerebras", "qwen-3-235b-a22b-instruct-2507"),
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
    """3 provider'a paralel sor, cevapları similarity matrix'ine dök, consensus skoru hesapla."""
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

    # Cosine (Cohere embed) veya Jaccard fallback
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

    # Consensus: off-diagonal ortalaması
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
