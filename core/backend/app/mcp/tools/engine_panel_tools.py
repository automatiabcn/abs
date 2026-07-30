# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Engine-panel MCP tools — what the ABS editor's side panels render.

A desktop editor holds an ``abs_mcp_`` token, so ``/mcp`` is the only door it
has: every ``/v1`` surface wants a panel cookie or an OAuth JWT. Three things
the product already computes were therefore invisible to it, and these tools
open exactly those, nothing more:

* ``quota_meter_status`` — the real per-provider counters (requests used, left,
  percent, throttle reason). ``quota_status`` only ever reported which keys are
  configured plus breaker state, so a quota gauge built on it would have been a
  gauge with no needle.
* ``cascade_ask`` — one cascade call that answers WITH its provenance: which
  provider answered, which were tried on the way, tokens, latency, cost. The
  ``ask_*`` tools return bare text, so "which model did this?" — the failover
  story that is the reason to trust the answer — was dropped at the door.
* ``pipeline_run`` — a multi-model pipeline as STRUCTURED steps instead of the
  human-readable summary the existing pipeline tools flatten into text, so the
  delegation chain can be drawn rather than read.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from app.cascade import quota_meter
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


def _caller_user() -> Optional[str]:
    """The user this MCP token was minted for, when the transport carries one."""
    try:
        from app.mcp.context import get_mcp_caller

        _tenant, user = get_mcp_caller()
        return str(user) if user else None
    except Exception:  # pragma: no cover — defensive
        return None


def _caller_tenant() -> str:
    try:
        from app.mcp.context import get_mcp_caller

        tenant, _user = get_mcp_caller()
        if tenant:
            return str(tenant)
    except Exception:  # pragma: no cover — defensive
        pass
    return getattr(settings, "mcp_rag_tenant", None) or "default"


@mcp_server.tool()
@with_hooks("quota_meter_status")
async def quota_meter_status() -> str:
    """Live per-provider request quota for this tenant: used, left, percent,
    throttle state and reason. Providers with no known limit are reported as
    unlimited rather than shown as an empty gauge."""
    await tracker.bump("quota_meter_status")
    tenant = _caller_tenant()
    snapshot = quota_meter.get_all_status(tenant_id=tenant)
    # Say which providers actually have a key, so a full gauge on an
    # unconfigured provider cannot read as "ready to serve".
    server_keys = {
        "groq": bool(settings.groq_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "gemini": bool(settings.gemini_api_key),
        "cloudflare": bool(settings.cf_account_id and settings.cf_api_token),
        "cohere": bool(settings.cohere_api_key),
        "openrouter": bool(settings.openrouter_api_key),
    }
    # BYOK counts. Reading only the server's env told a user who had just added
    # their own key that the provider still had none — the panel asked them to
    # fix something and then ignored the fix.
    byok: set = set()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        byok = set(
            tenant_configured_providers(
                tenant_slug=tenant, user_subject=_caller_user()
            )
        )
    except Exception:  # noqa: BLE001 — BYOK lookup must never break the gauge
        byok = set()
    for name, row in snapshot.get("providers", {}).items():
        from_account = name in byok
        row["configured"] = bool(server_keys.get(name, False) or from_account)
        # Whose key is answering matters: "mine" and "the server's" are
        # different bills and different trust.
        row["key_source"] = (
            "account" if from_account else ("server" if server_keys.get(name) else "")
        )
    snapshot["limits"] = quota_meter.QUOTA_LIMITS
    snapshot["note"] = (
        "Counted by this server as calls go out — not fetched from the "
        "provider's own quota API. Calls made outside this server are not seen."
    )
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("cascade_ask")
async def cascade_ask(
    prompt: str,
    prefer: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
    use_cache: bool = True,
) -> str:
    """Ask the provider cascade and return the answer WITH its provenance:
    which provider answered, the failover trail, tokens, latency and estimated
    cost. Use this instead of ask_* when the caller shows the user where the
    answer came from."""
    await tracker.bump("cascade_ask")
    from app.cascade.orchestrator import call_with_cascade
    from app.providers.cascade import get_active_providers

    tenant = _caller_tenant()
    active = get_active_providers()
    if not active:
        return json.dumps(
            {
                "ok": False,
                "error": "no_provider_configured",
                "detail": "No provider has a usable key on this server.",
            },
            ensure_ascii=False,
        )
    primary = prefer.strip() or active[0]
    fallbacks = tuple(p for p in active if p != primary)

    started = time.perf_counter()
    try:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            fallbacks=fallbacks,
            max_tokens=max_tokens,
            temperature=temperature,
            use_cache=use_cache,
            tenant_id=tenant,
        )
    except Exception as exc:  # noqa: BLE001 — report, never raise into MCP
        return json.dumps(
            {
                "ok": False,
                "error": "cascade_failed",
                "detail": str(exc)[:400],
                "tried": list(active),
            },
            ensure_ascii=False,
        )

    tokens_in = int(getattr(resp, "tokens_in", 0) or 0)
    tokens_out = int(getattr(resp, "tokens_out", 0) or 0)
    cost: Dict[str, Any] = {}
    try:
        from app.chat.cost import estimate_call_cost_usd

        cost = estimate_call_cost_usd(
            provider=getattr(resp, "provider", None) or None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=getattr(resp, "model", None),
        )
    except Exception:  # noqa: BLE001 — cost is an annotation, not the answer
        cost = {}

    return json.dumps(
        {
            "ok": True,
            "text": getattr(resp, "text", "") or "",
            "provider": getattr(resp, "provider", "") or "",
            "model": getattr(resp, "model", "") or "",
            # The trail is empty on a cache hit: nothing was tried, and saying
            # "groq answered" there would invent a call that never happened.
            "providers_tried": list(getattr(resp, "providers_tried", []) or []),
            "cached": bool(getattr(resp, "cached", False)),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "cost_usd": cost.get("usd"),
            "cost_free": cost.get("free"),
        },
        ensure_ascii=False,
    )


def _pipeline_classes() -> Dict[str, Any]:
    """Imported lazily so this module costs nothing until a panel asks."""
    from app.pipelines.quality.analysis import QualAnalysisPipeline
    from app.pipelines.quality.code import QualCodePipeline
    from app.pipelines.quality.turkish import QualTrPipeline
    from app.pipelines.race.code import RaceCodePipeline
    from app.pipelines.race.general import RaceGeneralPipeline

    return {
        "qual_code": QualCodePipeline,
        "qual_analysis": QualAnalysisPipeline,
        "qual_tr": QualTrPipeline,
        "race": RaceGeneralPipeline,
        "race_code": RaceCodePipeline,
    }


@mcp_server.tool()
@with_hooks("pipeline_run")
async def pipeline_run(prompt: str, kind: str = "qual_code") -> str:
    """Run a multi-model pipeline and return its STEPS as structured data —
    step name, model, elapsed, ok — so the caller can draw the delegation chain
    instead of parsing a summary line. `kind`: qual_code | qual_analysis |
    qual_tr | race | race_code."""
    await tracker.bump("pipeline_run")
    known = _pipeline_classes()
    if kind not in known:
        return json.dumps(
            {"ok": False, "error": "unknown_pipeline", "known": sorted(known)},
            ensure_ascii=False,
        )
    try:
        result = await known[kind]().run(prompt)
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "pipeline_failed", "detail": str(exc)[:400]},
            ensure_ascii=False,
        )

    steps: List[Dict[str, Any]] = []
    for step in getattr(result, "steps", []) or []:
        meta = getattr(step, "meta", {}) or {}
        steps.append(
            {
                "name": getattr(step, "name", ""),
                "model": getattr(step, "model", ""),
                "elapsed_ms": getattr(step, "elapsed_ms", 0),
                "ok": bool(getattr(step, "ok", False)),
                "error": getattr(step, "error", None),
                "tokens_in": meta.get("tokens_in"),
                "tokens_out": meta.get("tokens_out"),
            }
        )
    return json.dumps(
        {
            "ok": getattr(result, "error", None) is None,
            "pipeline": getattr(result, "pipeline_type", kind),
            "steps": steps,
            "total_elapsed_ms": getattr(result, "total_elapsed_ms", 0),
            "text": getattr(result, "final_response", "") or "",
            "error": getattr(result, "error", None),
            "trace_id": getattr(result, "workflow_trace_id", None),
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.extend(["quota_meter_status", "cascade_ask", "pipeline_run"])

__all__ = ["quota_meter_status", "cascade_ask", "pipeline_run", "REGISTERED_TOOLS"]


def _unused() -> Optional[str]:  # pragma: no cover — keeps Optional imported
    return None


# --- BYOK provider keys ------------------------------------------------------
#
# The Engine panel can say "cohere: no key — nothing is routed here" and, until
# now, offer no way to fix it: BYOK lived behind an admin-only HTTP route. These
# two close that loop from the editor, with a deliberately narrow boundary:
# a key set here belongs to the CALLING USER, never the tenant or the org. A
# delegated MCP token must not be able to rewrite an organisation's credentials.


@mcp_server.tool()
@with_hooks("provider_keys_list")
async def provider_keys_list() -> str:
    """Which providers this account has its own key for. Metadata only —
    plaintext keys are never returned, by this tool or any other."""
    await tracker.bump("provider_keys_list")
    from app.multitenant import provider_keys as _pk

    tenant = _caller_tenant()
    try:
        rows = _pk.list_provider_keys(tenant_slug=tenant)
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "keys_unavailable", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    return json.dumps(
        {"ok": True, "tenant": tenant, "keys": rows}, ensure_ascii=False, default=str
    )


@mcp_server.tool()
@with_hooks("provider_key_set")
async def provider_key_set(provider: str, value: str) -> str:
    """Store this account's own key for a provider (BYOK), encrypted at rest.
    The key is scoped to the CALLING USER — organisation-wide keys stay in the
    panel, so a delegated editor token cannot rewrite an org's credentials.
    The value is never echoed back."""
    await tracker.bump("provider_key_set")
    from app.multitenant import provider_keys as _pk

    tenant = _caller_tenant()
    user = _caller_user()
    if not user:
        # Without a user identity there is no safe owner to attach the key to;
        # falling back to the tenant would silently widen its scope.
        return json.dumps(
            {
                "ok": False,
                "error": "no_user_identity",
                "detail": "Sign in to ABS so the key can be stored against your account.",
            },
            ensure_ascii=False,
        )
    if not (value or "").strip():
        return json.dumps(
            {"ok": False, "error": "empty_value"}, ensure_ascii=False
        )
    try:
        _pk.set_provider_key(
            tenant_slug=tenant,
            owner_type=_pk.OWNER_USER,
            owner_id=user,
            provider=provider,
            value=value,
        )
    except ValueError as exc:
        return json.dumps(
            {"ok": False, "error": "invalid_request", "detail": str(exc)},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "store_failed", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    return json.dumps(
        {"ok": True, "provider": provider, "owner": "user", "stored": True},
        ensure_ascii=False,
    )


@mcp_server.tool()
@with_hooks("provider_key_delete")
async def provider_key_delete(provider: str) -> str:
    """Remove this account's own key for a provider. Only the caller's own key
    is removable here — the org's key is not this token's to delete."""
    await tracker.bump("provider_key_delete")
    from app.multitenant import provider_keys as _pk

    tenant = _caller_tenant()
    user = _caller_user()
    if not user:
        return json.dumps(
            {"ok": False, "error": "no_user_identity"}, ensure_ascii=False
        )
    try:
        removed = _pk.delete_provider_key(
            tenant_slug=tenant,
            owner_type=_pk.OWNER_USER,
            owner_id=user,
            provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "delete_failed", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, "provider": provider, "removed": bool(removed)})


REGISTERED_TOOLS.extend(
    ["provider_keys_list", "provider_key_set", "provider_key_delete"]
)
