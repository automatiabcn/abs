# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Email classification — keyword heuristics behind an LLM-ready interface.

Patterns cover the supported product languages; non-ASCII keywords are written as
escapes so the source stays ASCII while matching the same words."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = ["EmailCategory", "EmailClassification", "classify_email"]


@dataclass(frozen=True, slots=True)
class EmailCategory:
    name: str
    priority: int  # higher = more urgent


CATEGORIES = {
    "urgent": EmailCategory("urgent", 100),
    "billing": EmailCategory("billing", 60),
    "tech": EmailCategory("tech", 40),
    "sales": EmailCategory("sales", 20),
    "spam": EmailCategory("spam", -10),
}


@dataclass(slots=True)
class EmailClassification:
    category: str
    priority: int
    confidence: float
    reasons: list[str]


_PATTERNS: dict[str, tuple[str, ...]] = {
    "urgent": (
        r"\burgent\b",
        r"\basap\b",
        r"\bcritical\b",
        r"\bimmediately\b",
        r"acil",
        r"derhal",
        r"production\s+down",
    ),
    "billing": (
        r"\binvoice\b",
        r"\bbilling\b",
        r"\bpayment\b",
        r"\bstripe\b",
        r"fatura",
        r"\u00f6deme",
        r"refund",
    ),
    "tech": (
        r"\bbug\b",
        r"\berror\b",
        r"\bstacktrace\b",
        r"\b500\b",
        r"\bapi\b",
        r"hata",
    ),
    "sales": (
        r"\bdemo\b",
        r"\bquote\b",
        r"\bproposal\b",
        r"\bpricing\b",
        r"teklif",
        r"fiyat",
    ),
    "spam": (
        r"\bclick\s+here\b",
        r"\bbitcoin\b",
        r"\bwinner\b",
        r"\bcongratulations\b",
        r"\bnigerian\s+prince\b",
    ),
}


def classify_email(subject: str, body: str) -> EmailClassification:
    text = f"{subject}\n{body}".lower()
    hits: dict[str, list[str]] = {k: [] for k in CATEGORIES}
    for cat, patterns in _PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text):
                hits[cat].append(pat)

    scored: list[tuple[str, int]] = sorted(
        (
            (cat, CATEGORIES[cat].priority * len(matches))
            for cat, matches in hits.items()
            if matches
        ),
        key=lambda x: -x[1],
    )

    if not scored:
        return EmailClassification(
            category="tech",
            priority=CATEGORIES["tech"].priority,
            confidence=0.2,
            reasons=["no_pattern_matched_default_to_tech"],
        )

    top, _ = scored[0]
    confidence = min(1.0, 0.4 + 0.2 * len(hits[top]))
    return EmailClassification(
        category=top,
        priority=CATEGORIES[top].priority,
        confidence=confidence,
        reasons=[f"hit:{p}" for p in hits[top]],
    )
