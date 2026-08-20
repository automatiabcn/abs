# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What this install can do right now, and the one key that would change it.

ABS runs on the developer's own keys, so a fresh install is not broken or
working — it is somewhere on a slope, and the product should say where. This
tool answers the three questions a new install actually raises: what works,
what does not, and which single key is worth getting next.

The two numbers it reports are read from what is *resolved*, not what is
*configured*. `embedding_backend="auto"` that fell through to `mock` is not an
embedding source — it hashes the text — so it is reported as none. A capability
this tool calls available is one that would really run.
"""

from __future__ import annotations

import json
from typing import Optional, List

from app.capabilities import (
    CHAT_PROVIDERS,
    FREE_TO_START,
    HOW_TO_GET,
    assess,
    summarise,
)
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


def _subscriptions() -> list:
    """What the customer may already be paying for, detected — never probed.

    Detection is a file-system check. The probe costs a real call against the
    customer's own subscription, so it never runs as part of a readout: a page
    that quietly spends somebody's allowance every time it loads is a page
    they will learn to avoid.
    """
    try:
        from app.providers.subscription import detect_all

        return detect_all()
    except Exception:  # noqa: BLE001 — a readout must not fail the panel
        return []


def _local_providers() -> set[str]:
    """Providers configured by URL rather than by key — no key to paste.

    Read from the cascade rather than listed again here: a second list is a
    second thing to forget when a local runtime is added.
    """
    try:
        from app.providers.cascade import LOCAL_URL_ATTR

        return {str(p).lower() for p in LOCAL_URL_ATTR}
    except Exception:  # noqa: BLE001
        # Unknown is "takes a key": offering a key box for something that does
        # not need one is a smaller failure than hiding a provider that does.
        return set()


def _configured_providers() -> set[str]:
    """Every provider this caller can actually use: theirs, then the server's."""
    names: set[str] = set()
    try:
        from app.providers.cascade import get_active_providers

        names |= {str(p).lower() for p in get_active_providers()}
    except Exception:  # noqa: BLE001 — a readout must not fail the panel
        pass
    try:
        from app.mcp.context import get_mcp_caller
        from app.providers.byok import byok_providers

        tenant, user = get_mcp_caller()
        names |= {str(p).lower() for p in byok_providers(tenant, user)}
    except Exception:  # noqa: BLE001
        pass
    return names


def _resolved_embedding_backend() -> str:
    """The backend that will really run, with "auto" already resolved.

    Reading `settings.embedding_backend` alone would report "auto" as if it
    were a source. It is a preference; `resolve_backend` is the answer.
    """
    requested = getattr(settings, "embedding_backend", "auto")
    try:
        from app.rag.embedding_bge import resolve_backend

        return str(resolve_backend(requested) or "").lower()
    except Exception:  # noqa: BLE001
        # Unknown is not "none" and not "fine": fall back to the raw setting,
        # which `assess` will refuse to treat as a source unless it names one.
        return str(requested or "").lower()


def _unusable_now() -> dict[str, str]:
    """Providers that have a key and still cannot answer this minute.

    Rate limits and open breakers are temporary, and the difference matters:
    a throttled provider must not be counted as working, and must not be
    mistaken for a missing key either — telling somebody to buy what they
    already own is worse advice than saying nothing.
    """
    from datetime import datetime, timezone

    from app.capabilities import minutes_to_utc_midnight, rest_reason

    down: dict[str, str] = {}
    tenant = None
    try:
        from app.mcp.context import get_mcp_caller

        tenant, _user = get_mcp_caller()
    except Exception:  # noqa: BLE001
        tenant = None

    to_midnight = minutes_to_utc_midnight(datetime.now(timezone.utc))

    try:
        from app.cascade.breaker import default_breaker

        for raw, value in (default_breaker.snapshot() or {}).items():
            # Breaker keys are tenant-namespaced once a call has been made —
            # and only THIS tenant's breaker says anything about this tenant.
            # Collapsing every tenant's key onto the provider name made B's
            # open breaker mark the provider "resting" for A (2026-08-18).
            raw_s = str(raw)
            if "|" in raw_s:
                key_tenant, name = raw_s.rsplit("|", 1)
                if tenant is not None and key_tenant not in (str(tenant), "_global", "default"):
                    continue
            else:
                name = raw_s
            name = name.lower()
            if str((value or {}).get("state", "")).lower() == "open":
                down[name] = rest_reason("breaker_open", minutes_to_utc_midnight=to_midnight)
    except Exception:  # noqa: BLE001 — an unreadable breaker is not an open one
        pass

    # A provider whose last call failed permanently is not resting, it is
    # not answering — and unlike a quota it will not clear at midnight.
    try:
        from app.cascade import provider_health as _health

        for name, row in _health.snapshot(str(tenant) if tenant else None).items():
            if row.get("reason"):
                down.setdefault(str(name).lower(), str(row["reason"]))
    except Exception:  # noqa: BLE001
        pass

    try:
        from app.cascade import quota_meter

        for name in list(getattr(quota_meter, "QUOTA_LIMITS", {})):
            throttled, code = quota_meter.is_throttled(name, tenant_id=tenant or "default")
            if throttled:
                down.setdefault(
                    str(name).lower(),
                    rest_reason(code, minutes_to_utc_midnight=to_midnight),
                )
    except Exception:  # noqa: BLE001
        pass

    return down


@mcp_server.tool()
@with_hooks("capability_status")
async def capability_status() -> str:
    """What this install can do with the keys it has, and what one more buys.

    Returns every capability with `available`, why it is not, and the cheapest
    real way to unlock it — free tiers named first, because the product routes
    to free providers by default and the cheapest unlock is the honest one to
    recommend.
    """
    await tracker.bump("capability_status")
    providers = _configured_providers()
    backend = _resolved_embedding_backend()
    down = _unusable_now()
    try:
        from app.sandbox import runner as _sandbox

        sandbox_ok: Optional[bool] = bool(_sandbox.available_mechanism())
    except Exception:  # noqa: BLE001 — unknown is not "no"
        sandbox_ok = None
    states = assess(
        providers, embedding_backend=backend, unusable_now=down, sandbox_available=sandbox_ok
    )
    return json.dumps(
        {
            "ok": True,
            "providers": sorted(providers),
            "resting": down,
            "embedding_backend": backend,
            # Subscriptions the customer may already pay for. Not keys — a
            # binary they install and sign into once. Reported separately
            # because the answer to "how do I connect this?" is a different
            # sentence, and putting them in the key list would ask somebody to
            # paste a credential that does not exist.
            "subscriptions": [
                {
                    "key": st.key,
                    "label": st.label,
                    "installed": st.installed,
                    "signed_in": st.signed_in,
                    "ready": st.ready,
                    "detail": st.detail,
                    "install": st.install,
                    "sign_in": st.sign_in,
                    "next_step": st.next_step(),
                }
                for st in _subscriptions()
            ],
            # Where each key actually comes from, so the editor's "add a key"
            # picker reads this instead of keeping its own weaker copy. Two
            # sources for one fact drift, and the copy that drifts is the one
            # nobody remembers exists.
            "how_to_get": {
                p: {
                    "how": HOW_TO_GET.get(p, ""),
                    "free": p in FREE_TO_START,
                    # Already held. Telling somebody to go and get what they
                    # have is worse advice than saying nothing — the same rule
                    # the quota work landed on.
                    "configured": p in providers,
                    # A local runtime is configured by URL on the server; there
                    # is no key to paste. Seen live (08-02): ollama and mlx led
                    # a picker headed "which provider is this key for?", and
                    # choosing one asked for a key that does not exist.
                    "takes_key": p not in _local_providers(),
                }
                for p in sorted(CHAT_PROVIDERS)
            },
            "capabilities": [
                {
                    "key": s.capability.key,
                    "title": s.capability.title,
                    "promise": s.capability.promise,
                    "available": s.available,
                    "blocked_by": s.blocked_by,
                    "unlock_with": s.unlock_with,
                    "unlock_is_free": s.unlock_is_free,
                    "how_to": s.how_to,
                }
                for s in states
            ],
            "summary": summarise(states),
        },
        ensure_ascii=False,
    )


@mcp_server.tool()
@with_hooks("subscription_check")
async def subscription_check(name: str) -> str:
    """Ask a subscription CLI whether it can actually answer.

    Separate from `capability_status` on purpose: this one COSTS a call
    against the customer's own allowance, so it runs when somebody asks, not
    when a page loads. A readout that quietly spends your subscription every
    time you open it is one you learn to avoid.
    """
    await tracker.bump("subscription_check")
    try:
        from app.providers.subscription import probe

        st = probe(str(name or "").strip())
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)[:200]}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "key": st.key,
            "label": st.label,
            "installed": st.installed,
            "signed_in": st.signed_in,
            "ready": st.ready,
            "detail": st.detail,
            "next_step": st.next_step(),
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.extend(["capability_status", "subscription_check"])
