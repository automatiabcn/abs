# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""humanize_score: input metninin 'AI-written' izlenimi için heuristik skor.

SERVER humanizer/ modülünün hafif kopyası: özel işaretler (aşırı parallel yapı,
metinsel "certainly", "as an AI" gibi stock phrase'ler) basit bir sayaçla 0-1 arasında
skorlanır. 0 = insana benzer, 1 = AI izlenimi yüksek. Gelecek task'ta ML scorer ile
yer değiştirilebilir.
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
    r"\bsaygılarımla\b",
    r"\bumarım yardımcı olur\b",
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
    score: float  # 0..1, 1 = AI izlenimi yüksek
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

    # Uzun, düzgün cümleler → AI eğilimi yüksek olabilir (heuristik).
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    if avg_len > 22:
        matches.append(f"avg-sentence-len:{avg_len:.1f}")

    # Toplam skor: her match 0.12 ağırlık, upper cap 1.0
    raw = min(1.0, len(matches) * 0.12)
    return HumanizeScore(
        score=round(raw, 2),
        matches=matches,
        length=len(text),
        sentence_count=len(sentences),
    )
