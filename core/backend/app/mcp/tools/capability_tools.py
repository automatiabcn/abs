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
    states = assess(providers, embedding_backend=backend)
    return json.dumps(
        {
            "ok": True,
            "providers": sorted(providers),
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
