# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pipeline auto-routing for chat.

Picks one of the qual-* pipelines (or the `auto_direct` cascade) from keyword
and character-class signals in the user's last message. The router is
deterministic and side-effect free; the chat handler only consults it when
`pipeline="auto"` is requested.

Decision order matters — code and translation requests beat the plain
language/analysis routes when both patterns match. `race_code` is opt-in only
(never auto-selected) because parallel multi-model calls multiply cost.

Keyword patterns cover the supported product languages; non-ASCII characters are
written as escapes so the source stays ASCII while matching the same words.
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

_TR_DIACRITIC_RX = re.compile(r"[\u0131\u011f\u00fc\u015f\u00f6\u00e7\u011e\u00dc\u015e\u00d6\u00c7\u0130]")
_CODE_RX = re.compile(
    r"\b(kod|code|fonksiyon|function|class|api|endpoint|debug|hata|stack\s*trace|"
    r"bug|exception|tipe?|typescript|python|rust|golang|java|c\+\+)\b",
    re.IGNORECASE,
)
_TRANSLATE_RX = re.compile(
    r"\b("
    r"\u00e7evir|cevir|"           # TR + ASCII-folded
    r"terc\u00fcme|tercume|"
    r"translate|translation"
    r")\b",
    re.IGNORECASE,
)
_ANALYSIS_RX = re.compile(
    r"\b(analiz|kar\u015f\u0131la\u015ft\u0131r|compare|tradeoff|why|neden|rationale|"
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
