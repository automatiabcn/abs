# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Whose providers answer a caller, in what order.

One function, shared by the chat tool, the chat stream and the editor
agent, so the chain the panel shows is the chain that is walked. It lives
outside the MCP tool modules on purpose: those import the MCP server, the
server registers every tool, and anything that needs only the chain would
otherwise drag the whole tool surface in (and trip a circular import when
loaded first, as the editor agent's tests did).
"""

from __future__ import annotations

from typing import Any, Dict


def resolve_chain(prefer: str, tenant: str, user: str) -> Dict[str, Any]:
    """Whose providers answer this caller, in what order.

    Shared by the chat, its stream and the editor agent so the chain the
    panel shows is the chain that is walked (live finding, 07-31: the panel
    said "1. cerebras · your key" and the answer came from groq). Returns
    ``{"error": {...}}`` or ``{"primary", "fallbacks", "active", "tenant", "user"}``.
    """
    from app.providers.cascade import get_active_providers

    # The chain the PANEL shows is BYOK-aware and puts the caller's own keys
    # first; the chain this tool actually walked was not. One chain, both places.
    byok: frozenset = frozenset()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        byok = frozenset(
            tenant_configured_providers(tenant_slug=tenant, user_subject=user)
        )
    except Exception:  # noqa: BLE001 — a chain without BYOK is still a chain
        byok = frozenset()
    active = get_active_providers(extra_configured=byok)
    # Whose money: paid providers only on the caller's key, or the operator's
    # when the operator asks (or shared it). `prefer` is checked against the
    # same list — naming a provider is not a way past it.
    from app.providers.paid_access import refusal as _paid_refusal
    from app.providers.paid_access import restrict_chain

    active = restrict_chain(active, byok, user)
    if not active:
        return {
            "error": {
                "ok": False,
                "error": "no_provider_configured",
                "detail": "No provider has a usable key on this server.",
            }
        }
    wanted = (prefer or "").strip()
    if wanted and wanted not in active:
        why = _paid_refusal(wanted, byok, user) or (
            f"{wanted} is not a provider this caller can use here."
        )
        return {"error": {"ok": False, "error": "provider_not_available", "detail": why}}
    primary = wanted or active[0]
    fallbacks = tuple(p for p in active if p != primary)
    return {
        "primary": primary,
        "fallbacks": fallbacks,
        "active": active,
        "tenant": tenant,
        "user": user,
    }
