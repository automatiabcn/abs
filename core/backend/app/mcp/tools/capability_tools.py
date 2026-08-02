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
from typing import List

from app.capabilities import assess, summarise
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


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
            # Breaker keys are tenant-namespaced once a call has been made.
            name = str(raw).split("|")[-1].lower()
            if str((value or {}).get("state", "")).lower() == "open":
                down[name] = rest_reason("breaker_open", minutes_to_utc_midnight=to_midnight)
    except Exception:  # noqa: BLE001 — an unreadable breaker is not an open one
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
    states = assess(providers, embedding_backend=backend, unusable_now=down)
    return json.dumps(
        {
            "ok": True,
            "providers": sorted(providers),
            "resting": down,
            "embedding_backend": backend,
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


REGISTERED_TOOLS.extend(["capability_status"])
