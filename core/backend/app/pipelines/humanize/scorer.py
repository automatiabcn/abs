# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Humanize_score: heuristic score for how "AI-written" a text reads.

Counts tells — stock phrases ("as an AI", "in conclusion"), heavy parallel
structure, uniformly long sentences — and maps the hit count onto 0-1.
0 = reads human, 1 = reads machine-generated. It is a counter, not a
classifier: the score is only meaningful in aggregate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

STOCK_PHRASES = [
    r"\bas an ai\b",
    r"\bi (cannot|can't) provide\b",
    r"\bin conclusion\b",
    r"\bit's (important|worth) (to )?(note|noting)\b",
    r"\bhere (is|are) (a|some)\b",
    # Turkish stock phrases ("saygilarimla", "umarim yardimci olur"), escaped
    # Rather than written literally so the source stays ASCII. The dotless i
    # is significant: these must keep matching Turkish output.
    "\\bsayg\u0131lar\u0131mla\\b",
    "\\bumar\u0131m yard\u0131mc\u0131 olur\\b",
    r"\bdelve into\b",
    r"\boverall\b",
    r"\blastly\b",
    r"\bfurthermore\b",
    r"\bcrucially\b",
    r"\bthis reflects\b",
]

PARALLEL_MARKERS = ["firstly", "secondly", "thirdly", "moreover", "however"]


@dataclass
class HumanizeScore:
    score: float  # 0..1, higher = reads more machine-generated
    matches: List[str]
    length: int
    sentence_count: int


def humanize_score_text(text: str) -> HumanizeScore:
    if not text:
        return HumanizeScore(score=0.0, matches=[], length=0, sentence_count=0)

    lower = text.lower()
    matches: List[str] = []

    for pat in STOCK_PHRASES:
        if re.search(pat, lower):
            matches.append(pat)

    parallel_hits = sum(lower.count(m) for m in PARALLEL_MARKERS)
    if parallel_hits >= 3:
        matches.append(f"parallel-markers:{parallel_hits}")

    # Uniformly long sentences are a weak tell on their own, so this only
    # Contributes one more hit rather than dominating the score.
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    if avg_len > 22:
        matches.append(f"avg-sentence-len:{avg_len:.1f}")

    # Each hit is worth 0.12, capped at 1.0.
    raw = min(1.0, len(matches) * 0.12)
    return HumanizeScore(
        score=round(raw, 2),
        matches=matches,
        length=len(text),
        sentence_count=len(sentences),
    )
