# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12 / Brief 3 R2 — pipeline auto-routing for chat.

Picks one of the qual-* pipelines (or `auto_direct` cascade) based on
keyword + character-class signals in the user's last message. The router
is deterministic + side-effect free; the chat handler only consults it
when `pipeline="auto"` is requested.

Decision order matters — code/translate beat plain TR/analysis when both
patterns match. `race_code` is opt-in only (never auto-selected) because
parallel multi-model calls multiply cost.
"""

from __future__ import annotations

import re
from typing import Final, Literal

PipelineId = Literal[
    "auto_direct",
    "qual_code",
    "qual_tr",
    "qual_analysis",
    "qual_translate",
    "race_code",
]

PIPELINE_OPTIONS: Final[tuple[PipelineId, ...]] = (
    "auto_direct",
    "qual_code",
    "qual_tr",
    "qual_analysis",
    "qual_translate",
    "race_code",
)

_TR_DIACRITIC_RX = re.compile(r"[ığüşöçĞÜŞÖÇİ]")
_CODE_RX = re.compile(
    r"\b(kod|code|fonksiyon|function|class|api|endpoint|debug|hata|stack\s*trace|"
    r"bug|exception|tipe?|typescript|python|rust|golang|java|c\+\+)\b",
    re.IGNORECASE,
)
_TRANSLATE_RX = re.compile(
    r"\b("
    r"çevir|cevir|"           # TR + ASCII-folded
    r"tercüme|tercume|"
    r"translate|translation"
    r")\b",
    re.IGNORECASE,
)
_ANALYSIS_RX = re.compile(
    r"\b(analiz|karşılaştır|compare|tradeoff|why|neden|rationale|"
    r"avantaj|disadvantage)\b",
    re.IGNORECASE,
)


def detect_pipeline(user_msg: str) -> PipelineId:
    """Return the recommended pipeline id for a user message.

    Empty / whitespace-only input falls through to ``auto_direct`` so the
    cascade still runs (the chat handler decides what error to raise).
    """
    text = (user_msg or "").strip()
    if not text:
        return "auto_direct"

    # Translate beats both TR + analysis when the user explicitly asks
    # for a translation.
    if _TRANSLATE_RX.search(text):
        return "qual_translate"

    if _CODE_RX.search(text):
        return "qual_code"

    if _ANALYSIS_RX.search(text):
        return "qual_analysis"

    if _TR_DIACRITIC_RX.search(text):
        return "qual_tr"

    return "auto_direct"


__all__ = ["PIPELINE_OPTIONS", "PipelineId", "detect_pipeline"]
