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
# Measured, not guessed (08-01): cerebras' llama3.1-8b was retired upstream —
# the entry sat here wrong and invisible until BYOK promoted cerebras and Tab
# went silent. gpt-oss-120b answers in 327ms with an EMPTY completion (it is a
# reasoning model and spends the 80-token budget thinking); gemma-4-31b answers
# in 350ms with the right insertion. groq stays first on latency.
#
# Measured again (08-18) after Groq retired llama-3.1-8b-instant on 08-16 and
# Tab went silent a second time, for two days: qwen3.6-27b with reasoning OFF
# inserts `n % 2 != 0` in 226ms; with reasoning on it writes 80 tokens of
# <think> and nothing else; gpt-oss-20b at low effort answers in ~400ms but
# echoes the prefix. So: qwen3.6 first, reasoning off. The retirement itself
# is now watched by `providers/catalog_watch.py` — a pinned model that leaves
# the live catalogue is reported, not discovered by a silent Tab.
_FAST_MODELS = {
    "groq": "qwen/qwen3.6-27b",
    "cerebras": "gemma-4-31b",
}
# Per-model call knobs; the adapter turns qwen3.6 reasoning off by itself, the
# entry here is the explicit statement so a future model swap has to decide.
_FAST_KWARGS = {
    "groq": {"reasoning_effort": "none"},
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


def _free_fast_chain(
    tenant_id: Optional[str] = None, user_subject: Optional[str] = None
) -> list:
    """The fastest free provider we have a completion model for.

    BYOK counts here too. The panel promises "the providers you supplied a
    key for come first", and Tab is the feature a developer touches hundreds
    of times a day — answering it from the operator's key while the user's
    own sits unused makes that promise false where it is felt most.
    """
    try:
        from app.providers.cascade import get_active_providers

        extra: frozenset = frozenset()
        if tenant_id:
            try:
                from app.multitenant.provider_keys import tenant_configured_providers

                extra = frozenset(
                    tenant_configured_providers(
                        tenant_slug=tenant_id, user_subject=user_subject
                    )
                )
            except Exception as exc:  # noqa: BLE001 — BYOK is a bonus, never a blocker
                logger.debug("fim BYOK lookup skipped: %s", exc)
        # Two different questions, kept apart. `_FAST_MODELS` answers "can we
        # even prompt this one for a fill-in-the-middle?" — a capability, local
        # to FIM. The ORDER is a routing opinion, and it belongs in one place
        # rather than being re-derived from the cost-first default here.
        from app.cascade.routing import INSTANT, chain_for

        usable = [
            name
            for name in get_active_providers(skip_paid=True, extra_configured=extra)
            if name in _FAST_MODELS
        ]
        return chain_for(INSTANT, usable) or usable
    except Exception as exc:  # noqa: BLE001
        logger.debug("fim provider lookup failed: %s", exc)
    return []


async def complete(
    prefix: str,
    suffix: str = "",
    *,
    language: str = "",
    tenant_id: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> Dict[str, object]:
    """Return the text to insert at the cursor, or an empty string.

    Never raises and never blocks past the timeout: the editor calls this on a
    keystroke pause and an empty result is a normal, silent outcome.
    """
    prefix = (prefix or "")[-_MAX_PREFIX:]
    suffix = (suffix or "")[:_MAX_SUFFIX]
    if not prefix.strip():
        return {"text": "", "provider": "", "ms": 0, "ok": False}

    chain = _free_fast_chain(tenant_id, user_subject)
    if not chain:
        return {
            "text": "",
            "provider": "",
            "ms": 0,
            "ok": False,
            "note": "no fast free provider",
        }

    # Try at most two. One provider was a single point of silence: when
    # cerebras' pinned model was retired upstream, Tab simply stopped
    # answering and nothing said why (08-01). A second attempt keeps the
    # feature alive through a stale pin or a momentary outage; a third would
    # cost more latency than a completion is worth.
    from app.providers.registry import get_provider

    last_provider = ""
    # Whether any provider got as far as returning something. An empty
    # completion from a model that looked is a real answer and the editor
    # should remember it; an empty completion because every provider threw
    # is an outage and must not stick. Both leave this loop by the same
    # door, so the difference has to be carried out with them.
    answered = False
    for provider_name in chain[:2]:
        last_provider = provider_name
        started = time.monotonic()
        # A provider the caller supplied a key for is only usable if the key
        # travels with the call. The cascade resolves per-owner keys for its
        # callers; Tab bypasses the cascade for latency, so it must do the
        # same lookup itself — without it, BYOK put cerebras first and the
        # adapter answered "api key is not configured" (found in review,
        # 08-01: the promotion was real, the credential never followed).
        call_kwargs: dict = {}
        if tenant_id and (user_subject or tenant_id):
            try:
                from app.multitenant.provider_keys import resolve_provider_key

                owner_key = resolve_provider_key(
                    provider_name,
                    tenant_slug=tenant_id,
                    user_subject=user_subject,
                    include_global=False,
                )
                if owner_key:
                    call_kwargs["api_key"] = owner_key
            except Exception as exc:  # noqa: BLE001 — never block a completion
                logger.debug("fim owner-key resolve skipped: %s", exc)
        try:
            provider = get_provider(provider_name)
            resp = await provider.call(
                _prompt(prefix, suffix, language),
                model=_FAST_MODELS[provider_name],
                max_tokens=_MAX_TOKENS,
                timeout=_TIMEOUT_S,
                **_FAST_KWARGS.get(provider_name, {}),
                **call_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — a missed completion is acceptable
            logger.debug("fim call failed on %s: %s", provider_name, exc)
            continue

        ms = int((time.monotonic() - started) * 1000)
        answered = True
        text = _clean(getattr(resp, "text", "") or "", prefix, suffix)
        if not text:
            # An empty answer from a model that spent its budget thinking is
            # not an outage — but it is also not a completion. Let the next
            # provider try before giving the editor nothing.
            logger.debug("fim empty completion from %s", provider_name)
            continue

        # FIM bypasses the cascade, so it must feed the meter itself — otherwise
        # every keystroke completion is invisible to the quota panel and the
        # per-model usage readout (live finding, 07-31).
        try:
            from app.cascade import quota_meter

            quota_meter.record_usage(
                provider_name,
                tenant_id=tenant_id or "default",
                tokens=int(getattr(resp, "tokens_in", 0) or 0)
                + int(getattr(resp, "tokens_out", 0) or 0),
                status_code=200,
                model=getattr(resp, "model", "") or _FAST_MODELS[provider_name],
            )
        except Exception:  # noqa: BLE001 — metering is never worth a missed completion
            logger.debug("fim meter skipped", exc_info=True)
        # `ok` is the difference between "the model looked and had nothing to
        # add" and "nobody answered". Both arrive as an empty string, and the
        # editor caches what it is told: without this, one rate-limited minute
        # left Tab permanently silent at every position visited during it.
        return {
            "text": text,
            "provider": provider_name,
            "ms": ms,
            "tier": "free",
            "ok": True,
        }

    # Nothing to insert. `ok` separates the two ways of getting here: a model
    # that looked and had nothing to add (remember that, Tab is silent here
    # and asking again on every keystroke pause costs for no reason), and a
    # chain where nobody answered at all (do not remember that, or one bad
    # minute becomes a session of silence).
    return {"text": "", "provider": last_provider, "ms": 0, "ok": answered}


def multiline_ok(prefix: str) -> bool:
    """Whether a multi-line completion makes sense at this cursor.

    On an empty line inside a block, several lines help; mid-expression, one
    line is what the developer wants and more is noise.
    """
    last = (prefix or "").rsplit("\n", 1)[-1]
    return last.strip() == ""
