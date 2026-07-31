# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tab / fill-in-the-middle completion — the fast, high-frequency surface.

Autocomplete is judged on latency and on NOT getting in the way. Two rules
follow from that and shape everything here:

- A completion that arrives late, or that repeats what the developer is about
  to type, is worse than no completion at all — it interrupts flow. So this
  path takes ONE fast free provider, a tight timeout, and returns nothing on
  any doubt rather than a guess.
- It runs on every keystroke pause, so it must be cheap: free tier only (the
  product rule), a small token budget, and a windowed context — never the
  whole file.

The models on the free tier are chat models, not FIM models, so they answer
"fill the gap" by echoing the whole line back. The insertion is recovered
deterministically here (`_clean`), where it can be tested, rather than trusted
from the model.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# The context window sent to the model. Enough to be useful, small enough to
# stay fast and cheap on a keystroke-frequency call.
_MAX_PREFIX = 2000
_MAX_SUFFIX = 600
_MAX_TOKENS = 80
_TIMEOUT_S = 3.0
# A fast free model. The completion path never falls back to a paid provider —
# autocomplete cost would balloon, and a missed completion is acceptable.
_FAST_MODELS = {
    "groq": "llama-3.1-8b-instant",
    "cerebras": "llama3.1-8b",
}

_FENCE = re.compile(r"^```[a-zA-Z0-9+-]*\n?|\n?```$")


def _prompt(prefix: str, suffix: str, language: str) -> str:
    lang = language or "code"
    return (
        f"You are a {lang} autocomplete engine. Insert code at <CURSOR> so the "
        "file reads correctly. Reply with ONLY the text that goes at the cursor "
        "— no explanation, no markdown fences, and do NOT repeat the code that "
        "is already before or after the cursor.\n\n"
        f"{prefix}<CURSOR>{suffix}"
    )


def _clean(raw: str, prefix: str, suffix: str) -> str:
    """Recover just the insertion from a chat model's answer.

    The model is asked for the middle and tends to return the whole line, or
    to run on into a restatement of the suffix. Neither is wrong to say — it is
    our job to keep only the part that belongs at the cursor.
    """
    text = raw.strip("\n")
    text = _FENCE.sub("", text).strip("\n")
    if not text:
        return ""

    # Drop a leading replay of the prefix itself. Fast chat models sometimes
    # restate the whole snippet from the top despite the instruction, and the
    # current-line handling below cannot see past one line. Strip the longest
    # tail of the prefix the answer literally starts with — but only when that
    # overlap spans a line break; a shorter match is more likely the real
    # completion than an echo.
    for k in range(min(len(prefix), len(text)), 0, -1):
        tail = prefix[-k:]
        if "\n" not in tail:
            break
        if text.startswith(tail):
            text = text[k:]
            break

    # Drop a leading echo of the current line. Models replay it ("return a + b"
    # when the cursor sits after "    return "), sometimes with the indentation
    # too. Compare against the line's content without its leading indent but
    # WITH its trailing space, so the space that follows the echoed word — the
    # one already typed — is consumed with it.
    last_line = prefix[-200:].rsplit("\n", 1)[-1]
    cur = last_line.lstrip()
    if cur and text.lstrip().startswith(cur):
        text = text.lstrip()[len(cur):]

    # Stop before the model reproduces what already follows the cursor. It may
    # skip a short suffix line (a lone "]") and land on a later one, so cut at
    # the EARLIEST place any substantial suffix line reappears — not just the
    # first suffix line.
    cut = len(text)
    for sline in suffix.split("\n")[:5]:
        s = sline.strip()
        if len(s) >= 4:
            idx = text.find(s)
            if idx > 0:
                cut = min(cut, idx)
    text = text[:cut].rstrip("\n") if cut < len(text) else text

    # A completion that is only whitespace is not a completion.
    return text if text.strip() else ""


def _first_free_fast() -> Optional[str]:
    """The fastest free provider we have a completion model for."""
    try:
        from app.providers.cascade import get_active_providers

        for name in get_active_providers(skip_paid=True):
            if name in _FAST_MODELS:
                return name
    except Exception as exc:  # noqa: BLE001
        logger.debug("fim provider lookup failed: %s", exc)
    return None


async def complete(
    prefix: str,
    suffix: str = "",
    *,
    language: str = "",
) -> Dict[str, object]:
    """Return the text to insert at the cursor, or an empty string.

    Never raises and never blocks past the timeout: the editor calls this on a
    keystroke pause and an empty result is a normal, silent outcome.
    """
    prefix = (prefix or "")[-_MAX_PREFIX:]
    suffix = (suffix or "")[:_MAX_SUFFIX]
    if not prefix.strip():
        return {"text": "", "provider": "", "ms": 0}

    provider_name = _first_free_fast()
    if not provider_name:
        return {"text": "", "provider": "", "ms": 0, "note": "no fast free provider"}

    started = time.monotonic()
    try:
        from app.providers.registry import get_provider

        provider = get_provider(provider_name)
        resp = await provider.call(
            _prompt(prefix, suffix, language),
            model=_FAST_MODELS[provider_name],
            max_tokens=_MAX_TOKENS,
            timeout=_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — a missed completion is acceptable
        logger.debug("fim call failed: %s", exc)
        return {"text": "", "provider": provider_name, "ms": 0}

    ms = int((time.monotonic() - started) * 1000)
    text = _clean(getattr(resp, "text", "") or "", prefix, suffix)
    return {"text": text, "provider": provider_name, "ms": ms, "tier": "free"}


def multiline_ok(prefix: str) -> bool:
    """Whether a multi-line completion makes sense at this cursor.

    On an empty line inside a block, several lines help; mid-expression, one
    line is what the developer wants and more is noise.
    """
    last = (prefix or "").rsplit("\n", 1)[-1]
    return last.strip() == ""
