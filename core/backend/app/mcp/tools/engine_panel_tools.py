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
import logging
import os
import time
from typing import Any, Dict, List, Optional

from app.cascade import quota_meter
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

logger = logging.getLogger(__name__)

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
@with_hooks("workspace_set")
async def workspace_set(root: str = "") -> str:
    """Tell the server which project the caller has open.

    The editor calls this when it starts and whenever the folder changes, so
    every other tool can answer about the code in front of the developer
    instead of in general. Pass an empty root to say "no folder open".

    This exists because a tester opened a project on 2026-08-03, asked the chat
    about it, and got an answer about nothing: of the thirty-three tools the
    editor calls, only Composer was sending the workspace. Adding the argument
    to the other thirty-two would have left the thirty-fourth wrong again.
    """
    await tracker.bump("workspace_set")
    from app.workspace.current import set_workspace

    tenant = _caller_tenant()
    stored = set_workspace(tenant, _caller_user() or "", root)
    if root and stored is None:
        return json.dumps(
            {
                "ok": False,
                "error": "not_a_directory",
                "detail": f"{root} is not a directory this server can see. If the "
                          f"server runs in a container, the project has to be "
                          f"mounted into it at the same path.",
            },
            ensure_ascii=False,
        )
    # Say whether this project has been read, in the same round trip. The
    # editor uses it to offer indexing once, rather than leaving a developer to
    # discover — from an honest but unhelpful "not indexed yet" — that a
    # command exists and where.
    indexed = False
    if stored:
        try:
            # Asked of the graph, which is what the editor's index command
            # actually writes. This asked the standalone symbols.db, which that
            # command never touches — so the answer was always "no" and the
            # editor offered to index on every launch, for ever.
            from app.codegraph import graph as _graph
            from app.mcp.tools.codegraph_tools import _key_for

            indexed = _graph.count_symbols(key=_key_for(tenant, stored)) > 0
        except Exception as exc:  # noqa: BLE001 — not knowing means not indexed
            # Logged, because a bare `except: False` hid a NameError here for
            # an hour: `tenant` was not a local, the lookup raised, and the
            # answer was a plausible "not indexed yet" that no test could tell
            # from the truth. Swallowing has to be loud enough to find.
            logger.warning("workspace_index_check_failed err=%s", exc)
            indexed = False

    return json.dumps(
        {"ok": True, "workspace": stored, "indexed": indexed}, ensure_ascii=False
    )


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
    user = _caller_user()
    # The chain the PANEL shows is BYOK-aware and puts the caller's own keys
    # first; the chain this tool actually walked was not (live finding, 07-31:
    # the panel said "1. cerebras · your key" and the answer came from groq).
    # One chain, both places.
    byok: frozenset = frozenset()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        byok = frozenset(
            tenant_configured_providers(tenant_slug=tenant, user_subject=user)
        )
    except Exception:  # noqa: BLE001 — a chain without BYOK is still a chain
        byok = frozenset()
    active = get_active_providers(extra_configured=byok)
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

    # Answer about the project the developer has open, when there is one.
    #
    # Reported by the first tester (2026-08-03): provider connected, project
    # open, and the chat answered as if the repository did not exist. It did
    # not, as far as this tool was concerned — it received a question and
    # nothing else, while Composer next door was reading the workspace.
    #
    # Retrieval is the same code Composer uses, so the two cannot drift into
    # disagreeing about what is relevant. `used_files` goes back in the
    # response because the panel promises the developer knows what was sent;
    # context gathered silently would break that promise more quietly than not
    # gathering it at all.
    asked = prompt
    used_files: list = []
    try:
        from app.composer.runtime import relevant_files, workspace_files
        from app.mcp.tools.codegraph_tools import _key_for
        from app.workspace.current import current_workspace

        root = current_workspace(tenant, user or "")
        if root:
            # Keyed by the project, not the tenant. Ranking the files to send
            # is the whole of "the chat knows the project you have open", and
            # with the tenant key it consulted a graph the editor's index
            # command never writes to — so the ranking fell back to filenames
            # for exactly the customer who had bothered to index.
            picked = relevant_files(
                root, prompt, workspace_files(root), graph_key=_key_for(tenant, root)
            )
            if picked:
                blocks = "\n\n".join(
                    f"--- {rel} ---\n{body}" for rel, body in picked
                )
                asked = (
                    f"{prompt}\n\n"
                    f"Files from the project the developer has open "
                    f"({os.path.basename(root)}):\n\n{blocks}"
                )
                used_files = [rel for rel, _ in picked]
    except Exception as exc:  # noqa: BLE001
        # Retrieval failing must not cost the developer their answer — it costs
        # them the context, and the response says so rather than pretending.
        logger.warning("cascade_ask_workspace_context_failed err=%s", exc)

    started = time.perf_counter()
    try:
        resp = await call_with_cascade(
            asked,
            primary=primary,
            fallbacks=fallbacks,
            max_tokens=max_tokens,
            temperature=temperature,
            use_cache=use_cache,
            tenant_id=tenant,
            user_subject=user,
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
            # Which of the developer's files went with the question. The panel
            # tells them what it sent; context gathered silently would break
            # that promise more quietly than not gathering it at all.
            "used_files": used_files,
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
    # Ask the provider before storing (07-31: a key mangled in the input box
    # sat in the chain as green "ready" — readiness is breaker state, and a
    # never-called breaker is closed). A rejected key is NOT stored; a probe
    # that cannot reach the provider stores the key but says so honestly.
    from app.providers.key_probe import probe_provider_key

    probe = probe_provider_key(provider, value.strip())
    if probe.status == "rejected":
        return json.dumps(
            {
                "ok": False,
                "error": "key_rejected",
                "detail": f"{probe.detail} — the key was NOT stored.",
            },
            ensure_ascii=False,
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
    out: dict = {"ok": True, "provider": provider, "owner": "user", "stored": True}
    if probe.status == "valid":
        out["verified"] = True
    else:
        # unvalidated / unreachable — stored, but nobody has seen it work.
        out["verified"] = False
        out["note"] = probe.detail
    return json.dumps(out, ensure_ascii=False)


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


# --- The delegation chain ----------------------------------------------------


@mcp_server.tool()
@with_hooks("providers_chain")
async def providers_chain(skip_paid: bool = False) -> str:
    """The cascade in the order it will actually be tried for THIS caller:
    position, free or paid, whose key answers, breaker and throttle state.

    This is the delegation chain the product is sold on — 'the agent never
    stops' means nothing if you cannot see who is next. `skip_paid` shows the
    chain a workflow would run on, since workflows never use paid providers.
    """
    await tracker.bump("providers_chain")
    from app.providers.cascade import (
        PAID_PROVIDERS,
        get_active_providers,
        is_configured,
    )

    tenant = _caller_tenant()
    user = _caller_user()

    byok: set = set()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        byok = set(tenant_configured_providers(tenant_slug=tenant, user_subject=user))
    except Exception:  # noqa: BLE001 — a chain without BYOK is still a chain
        byok = set()

    try:
        chain = get_active_providers(
            skip_paid=skip_paid, extra_configured=frozenset(byok)
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "chain_unavailable", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )

    from app.cascade.breaker import default_breaker

    raw_breakers = default_breaker.snapshot() or {}
    breakers: Dict[str, Any] = {}
    for key, value in raw_breakers.items():
        # Breaker keys are tenant-namespaced once a call has been made.
        breakers[str(key).split("|")[-1]] = value

    steps: List[Dict[str, Any]] = []
    for position, name in enumerate(chain, start=1):
        throttled = False
        reason = ""
        try:
            throttled, reason = quota_meter.is_throttled(name, tenant_id=tenant)
        except Exception:  # noqa: BLE001
            throttled, reason = False, ""
        steps.append(
            {
                "position": position,
                "provider": name,
                "paid": name in PAID_PROVIDERS,
                # An account key both activates and PROMOTES a provider: pasting
                # a key is a statement of preference, so say whose key it is.
                "key_source": "account" if name in byok else ("server" if is_configured(name) else ""),
                "breaker": (breakers.get(name) or {}).get("state", "closed"),
                "throttled": bool(throttled),
                "throttle_reason": reason if throttled else "",
            }
        )

    return json.dumps(
        {
            "ok": True,
            "tenant": tenant,
            "skip_paid": skip_paid,
            "chain": steps,
            "note": (
                "Tried in this order; the first that answers wins. Providers you "
                "supplied a key for come first — a key is a statement of "
                "preference. Workflows always run the skip_paid chain."
            ),
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.append("providers_chain")


# --- The title bar's one reading ---------------------------------------------


@mcp_server.tool()
@with_hooks("title_status")
async def title_status() -> str:
    """Everything the editor's title bar shows, in one call.

    The title bar is read at a glance, dozens of times an hour, so it must not
    cost four round trips. Every number here is counted from live state; a
    reading that cannot be taken comes back as null, never as zero — an empty
    title bar is honest, a confident wrong number is not.

    - `providers.ready` is how many providers could answer RIGHT NOW: a key,
      a closed breaker, and not throttled. It moves as providers are added,
      run out of quota, or trip — which is the point of showing it.
    - `free_share` is the share of today's requests that free providers
      served. It is null until something has actually run: "0% delegated" and
      "nothing has run yet" are different statements.
    """
    await tracker.bump("title_status")
    from app.cascade.breaker import default_breaker
    from app.providers.cascade import PAID_PROVIDERS, get_active_providers, is_configured

    tenant = _caller_tenant()
    user = _caller_user()

    byok: set = set()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        byok = set(tenant_configured_providers(tenant_slug=tenant, user_subject=user))
    except Exception:  # noqa: BLE001 — BYOK is a bonus, never a blocker
        byok = set()

    providers_ready: List[str] = []
    providers_total = 0
    models: List[str] = []
    try:
        chain = get_active_providers(extra_configured=frozenset(byok))
        providers_total = len(chain)
        raw_breakers = default_breaker.snapshot() or {}
        breakers = {
            str(k).split("|")[-1]: v for k, v in raw_breakers.items()
        }
        for name in chain:
            if not (name in byok or is_configured(name)):
                continue
            if (breakers.get(name) or {}).get("state", "closed") != "closed":
                continue
            try:
                throttled, _reason = quota_meter.is_throttled(name, tenant_id=tenant)
            except Exception:  # noqa: BLE001
                throttled = False
            if throttled:
                continue
            providers_ready.append(name)
            # The default chat model is only the model a provider WOULD answer
            # with; the day's real traffic may have used others (a completion
            # model on Tab, a fast judge). Both belong in the count — distinct
            # models bound or exercised, never one-per-provider by fiat.
            try:
                from app.providers.registry import get_provider

                model = getattr(get_provider(name), "default_model", "")
            except Exception:  # noqa: BLE001
                model = ""
            if model and model not in models:
                models.append(model)
            try:
                used = quota_meter.get_remaining(name, tenant_id=tenant).get(
                    "models"
                ) or {}
                for m in used:
                    if m and m not in models:
                        models.append(m)
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001 — the bar degrades, it does not fail
        return json.dumps(
            {
                "ok": False,
                "error": "providers_unavailable",
                "detail": str(exc)[:200],
                "account": user or "",
                "providers": None,
                "free_share": None,
            },
            ensure_ascii=False,
        )

    free_share: Optional[float] = None
    requests_today: Optional[int] = None
    try:
        snapshot = quota_meter.get_all_status(tenant_id=tenant)
        total = 0
        free = 0
        for name, row in (snapshot.get("providers") or {}).items():
            used = int(row.get("total_requests") or 0)
            total += used
            if name not in PAID_PROVIDERS:
                free += used
        requests_today = total
        # Null until something ran: "0% delegated" and "nothing has run yet"
        # are different statements, and only one of them is true here.
        if total > 0:
            free_share = round(free / total * 100, 1)
    except Exception:  # noqa: BLE001
        requests_today = None

    return json.dumps(
        {
            "ok": True,
            "account": user or "",
            "tenant": tenant,
            "providers": {
                "ready": len(providers_ready),
                "total": providers_total,
                "names": providers_ready,
            },
            "models": models,
            "free_share": free_share,
            "requests_today": requests_today,
            "note": (
                "ready = has a key, breaker closed, not throttled. free_share "
                "is null until a request has been made."
            ),
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.append("title_status")


# --- Tab / fill-in-the-middle -------------------------------------------------


@mcp_server.tool()
@with_hooks("fim_complete")
async def fim_complete(prefix: str, suffix: str = "", language: str = "") -> str:
    """Text to insert at the cursor — the Tab / ghost-text completion.

    Fast, free-tier, and silent on doubt: an empty ``text`` is a normal answer,
    not an error. The editor calls this on a typing pause with a window of code
    around the cursor, not the whole file; the reply is one provider, capped
    tokens, tight timeout. Latency is reported so the client can back off when
    the network is slow.
    """
    await tracker.bump("fim_complete")
    from app.fim.complete import complete

    result = await complete(
        prefix,
        suffix,
        language=language,
        tenant_id=_caller_tenant(),
        user_subject=_caller_user(),
    )
    return json.dumps(result, ensure_ascii=False)


REGISTERED_TOOLS.append("fim_complete")
