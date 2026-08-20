# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Validate a provider key by asking the provider, before it is stored.

Live incident (07-31): a key was mangled while being typed into the panel and
the chain kept showing the provider as green "ready" — readiness is breaker
state, and a breaker that has never carried a call is closed. A stored key the
provider would reject is worse than no key: the cascade routes to it first,
burns a failure, and the user reads "ready" the whole time.

Every check here is the provider's cheapest authenticated read (a model list,
a token-verify) — no tokens are generated and nothing is billed. A provider
this module does not know is reported as unvalidated, never guessed at.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_S = 8.0

# provider -> (url, auth mode). "bearer" sends Authorization; "query" puts the
# key in the URL; "x-api-key" is Anthropic's header spelling.
_CHECKS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1/models", "bearer"),
    "cerebras": ("https://api.cerebras.ai/v1/models", "bearer"),
    "openrouter": ("https://openrouter.ai/api/v1/models", "bearer"),
    "cohere": ("https://api.cohere.com/v1/models", "bearer"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        "query",
    ),
    "anthropic": ("https://api.anthropic.com/v1/models", "x-api-key"),
    # Token verify authenticates the token itself; the account id the calls
    # will run under is server configuration, checked elsewhere.
    "cloudflare": (
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        "bearer",
    ),
}


@dataclass
class KeyProbeResult:
    # "valid" — the provider accepted the key.
    # "rejected" — the provider answered and said no; detail carries its words.
    # "unreachable" — no answer; the key is NOT condemned by a network fault.
    # "unvalidated" — no probe known for this provider.
    status: str
    detail: str = ""


def probe_provider_key(provider: str, value: str) -> KeyProbeResult:
    """Ask the provider whether this key authenticates. Never logs the key."""
    if not (value or "").strip():
        # Measured 08-01: an empty key reached the wire and came back
        # "could not be reached" — a network story about a key that was never
        # there. Callers read `unreachable` as "keep it, the fault was ours",
        # which is how a blank field would have been stored.
        return KeyProbeResult("rejected", "no key was given")
    check = _CHECKS.get((provider or "").strip().lower())
    if not check:
        return KeyProbeResult(
            "unvalidated", f"no live check known for {provider!r}"
        )
    url, mode = check
    try:
        if mode == "query":
            resp = httpx.get(url.format(key=value), timeout=_TIMEOUT_S)
        elif mode == "x-api-key":
            resp = httpx.get(
                url,
                headers={"x-api-key": value, "anthropic-version": "2023-06-01"},
                timeout=_TIMEOUT_S,
            )
        else:
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {value}"},
                timeout=_TIMEOUT_S,
            )
    except Exception as exc:  # noqa: BLE001 — a network fault is not a verdict
        logger.info("key probe unreachable provider=%s err=%s", provider, exc)
        return KeyProbeResult("unreachable", f"{provider} could not be reached")
    if resp.status_code == 200:
        return KeyProbeResult("valid")
    if resp.status_code in (401, 403):
        return KeyProbeResult(
            "rejected", f"{provider} rejected the key ({resp.status_code})"
        )
    if resp.status_code == 400:
        # Gemini answers 400 INVALID_ARGUMENT for a malformed key.
        return KeyProbeResult(
            "rejected", f"{provider} called the key malformed ({resp.status_code})"
        )
    return KeyProbeResult(
        "unreachable",
        f"{provider} answered {resp.status_code} — key not judged",
    )
