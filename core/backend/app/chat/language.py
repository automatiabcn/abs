# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Which language the developer is writing in, and whether an answer kept it.

Seen live (2026-09-01, RobotMarket): the developer wrote Turkish for eight
turns; after the transcript filled with English file names and one English
answer, the model drifted to "Sure! Which page would you like to tackle
next?". The instruction "reply in the language the developer wrote in" was
in the prompt the whole time. A mid-size model follows a concrete
instruction ("answer in Turkish") far more reliably than a relative one, so
the chat now detects the language and says it by name — and checks the
answer, so a drift is caught before the developer reads it.

Pure text heuristics: no model call, no dependency. The word lists live in
lang_data.json (data, not code); Turkish is typed with and without its
diacritics, so both spellings are listed.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Tuple

_DATA_PATH = os.path.join(os.path.dirname(__file__), "lang_data.json")
try:
    with open(_DATA_PATH, "r", encoding="utf-8") as _fh:
        _DATA: Dict[str, Any] = json.load(_fh)
except (OSError, ValueError):  # pragma: no cover - a missing data file is English-only, not broken
    _DATA = {}

_TR_CHARS = set(_DATA.get("tr_chars", ""))
_ES_CHARS = set(_DATA.get("es_chars", ""))
_TR_WORDS = frozenset(_DATA.get("tr_words", ()))
_ES_WORDS = frozenset(_DATA.get("es_words", ()))
_EN_WORDS = frozenset(_DATA.get("en_words", ()))
# Agglutinative suffixes are strong evidence on their own, especially in
# diacritic-free typing where the letters alone say nothing.
_TR_SUFFIXES = tuple(_DATA.get("tr_suffixes", ()))

NAMES: Dict[str, str] = {"tr": "Turkish", "es": "Spanish", "en": "English"}


def _prose_only(text: str) -> str:
    """Code, paths and identifiers are English in every language; drop them
    before counting, or a Turkish sentence about `app/routes.py` reads as
    half English."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[A-Za-z0-9_./-]+\.(py|ts|js|html|md|json|css|tsx|jsx|yml|yaml)\b", " ", text)
    text = re.sub(r"\b\w+_\w+\b", " ", text)  # snake_case identifiers
    return text


def scores(text: str) -> Dict[str, float]:
    """Evidence per language. Exposed for tests; callers use detect()."""
    prose = _prose_only(text or "")
    out = {"tr": 0.0, "es": 0.0, "en": 0.0}
    for ch in prose:
        if ch in _TR_CHARS:
            out["tr"] += 1.5
        elif ch in _ES_CHARS:
            out["es"] += 1.5
    words = re.findall(r"[^\W\d_]+", prose.lower())
    for w in words:
        if w in _TR_WORDS:
            out["tr"] += 2
        elif w in _ES_WORDS:
            out["es"] += 2
        elif w in _EN_WORDS:
            out["en"] += 2
        elif len(w) > 4 and w.endswith(_TR_SUFFIXES):
            out["tr"] += 0.5
    return out


def detect(text: str) -> str:
    """'tr' | 'es' | 'en' | '' (not enough evidence to say)."""
    s = scores(text)
    best = max(s, key=lambda k: s[k])
    if s[best] < 2:
        return ""
    ordered = sorted(s.values(), reverse=True)
    # A clear winner, not a coin toss between two.
    if len(ordered) > 1 and ordered[0] - ordered[1] < 1.5:
        return ""
    return best


def name(code: str) -> str:
    return NAMES.get(code, "")


def drifted(expected: str, answer: str) -> Tuple[bool, str]:
    """Did an answer leave the developer's language?

    Returns (drifted, detected). Only a confident, contradicting detection
    counts: a short answer, an answer that is mostly code, or one the
    heuristic cannot place never trips this — a false "regenerate" costs a
    provider call and shows the developer a second, different answer.
    """
    if expected not in NAMES:
        return False, ""
    prose = _prose_only(answer or "")
    if len(re.findall(r"[^\W\d_]{3,}", prose)) < 12:
        return False, ""
    got = detect(answer)
    if not got or got == expected:
        return False, got
    s = scores(answer)
    # The expected language must be nearly absent, not merely outscored:
    # a Turkish answer quoting an English error message still is Turkish.
    if s[expected] >= s[got] * 0.5:
        return False, got
    return True, got
