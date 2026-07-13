# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q7 Phase A + BUG-29 — /v1/graph router.

Tenant-aware Cypher / ingest / NL-query / schema / seed endpoints. Auth
flips from the legacy cookie-only `current_admin` dep to the panel-or-bearer
`get_admin_or_bearer_auth_context` so that:

* the Next.js `/admin/graph` console (cookie session) can call without
  minting a JWT,
* CI / future MCP clients can hit the same routes with a Bearer token,
* every Cypher receives a `$tenant_id` parameter automatically and the
  response is post-filtered to drop rows whose nodes belong to a different
  tenant — defense-in-depth against malformed user queries (T-015 parity).

Neo4j outages return 503 with `neo4j_unavailable` instead of leaking 500.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from pydantic import BaseModel

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.config import settings
from app.integrations.neo4j_client import Neo4jClient
from app.integrations.neo4j_seed import ensure_tenant_seed

router = APIRouter(prefix="/v1/graph", tags=["graph"])
logger = logging.getLogger(__name__)

_DESTRUCTIVE = ("DELETE", "DROP", "REMOVE", "DETACH DELETE", "CREATE", "MERGE", "SET")
_TENANT_PARAM = "tenant_id"


class CypherRequest(BaseModel):
    cypher: str
    params: dict = {}


class IngestRequest(BaseModel):
    entities: List[dict]
    relations: List[dict] = []


class NLQueryRequest(BaseModel):
    intent: str
    locale: str = "tr"


def _is_destructive(cypher: str) -> bool:
    upper = cypher.upper()
    return any(kw in upper for kw in _DESTRUCTIVE)


# Clauses that step outside "tenant-scoped graph read/write" entirely: stored
# procedures (CALL apoc.* / dbms.* — SSRF via apoc.load.json, file reads,
# `CALL dbms.listConfig` info-disclosure, APOC-based destructive writes that
# the _DESTRUCTIVE blocklist misses), external data loading, and bulk
# iteration. None are used anywhere in the app or its templates, so blocking
# them on the user-driven Cypher paths is a pure hardening with no legitimate
# loss. Unlike _DESTRUCTIVE these are NOT confirm-bypassable — there is no
# "I'm sure" path to an SSRF primitive on a tenant query endpoint.
_FORBIDDEN_CLAUSE_RE = re.compile(
    r"(?:\bCALL\b|\bLOAD\s+CSV\b|\bFOREACH\b|\bPERIODIC\s+COMMIT\b|\bUSING\s+PERIODIC\b)",
    re.IGNORECASE,
)
# Cypher comments: /* block */ and // line. Neo4j ignores them, so an attacker
# can split a multi-word clause across one (`LOAD /*x*/ CSV`) to slip past the
# regex while the parser still executes LOAD CSV. Strip comments before the
# keyword scan. Only used for the SECURITY check — the original cypher is what
# actually runs — so over-stripping can only over-block (safe), never under-block.
_CYPHER_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def _has_forbidden_clause(cypher: str) -> bool:
    """True if the Cypher uses a stored-procedure / data-loading / bulk-iter
    clause that must never run on the tenant-scoped query endpoints."""
    stripped = _CYPHER_COMMENT_RE.sub(" ", cypher or "")
    return bool(_FORBIDDEN_CLAUSE_RE.search(stripped))


def _resolve_tenant(auth: AuthContext) -> str:
    tenant = (auth.tenant_id or "").strip()
    if not tenant:
        # The cookie path falls back to "default" inside _admin_cookie_context,
        # but a Bearer caller without a `tnt` claim can still slip through —
        # explicit 403 keeps multi-tenant isolation honest.
        raise HTTPException(403, "missing_tenant_claim")
    return tenant


def _filter_rows_by_tenant(rows: list[dict], tenant_id: str) -> list[dict]:
    """Drop rows whose returned nodes/maps carry a `tenant_id` not matching
    the caller. Rows without `tenant_id` keys (scalars, counts, raw IDs) pass
    through — Cerbos + the `$tenant_id` param injection are the upstream
    guards; this is the last-line filter for misbehaving Cypher.
    """
    safe: list[dict] = []
    for row in rows:
        leak = False
        for value in row.values():
            tid = _extract_tenant(value)
            if tid is not None and tid != tenant_id:
                leak = True
                break
        if not leak:
            safe.append(row)
    return safe


def _extract_tenant(value: Any) -> str | None:
    """Recursively look for a `tenant_id` key inside dict-like Neo4j rows."""
    if isinstance(value, dict):
        if "tenant_id" in value:
            tid = value.get("tenant_id")
            return str(tid) if tid is not None else None
        for v in value.values():
            found = _extract_tenant(v)
            if found is not None:
                return found
    if isinstance(value, list):
        for v in value:
            found = _extract_tenant(v)
            if found is not None:
                return found
    return None


async def _safe_query(
    cli: Neo4jClient, cypher: str, params: dict
) -> list[dict]:
    try:
        return await cli.query(cypher, params)
    except ServiceUnavailable as exc:
        logger.warning("neo4j_unavailable cypher=%s err=%s", cypher[:80], exc)
        raise HTTPException(503, "neo4j_unavailable") from exc
    except Neo4jError as exc:
        logger.info("neo4j_query_error cypher=%s err=%s", cypher[:80], exc)
        raise HTTPException(400, f"cypher_error: {exc.message or exc}") from exc


@router.get("/health")
async def health(
    _auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    client = Neo4jClient()
    ok = await client.health()
    return {"ok": ok, "uri": settings.neo4j_uri}


@router.get("/schema")
async def schema(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    """Return live schema scoped to the caller's tenant. Reflects the real
    graph — an empty tenant returns empty label/relationship lists (the UI
    renders an honest "no nodes/relationships yet" hint) rather than seeded
    placeholder labels that would imply data exists when it doesn't."""
    tenant = _resolve_tenant(auth)
    client = Neo4jClient()
    rows = await _safe_query(
        client,
        "MATCH (n) WHERE n.tenant_id = $tenant_id "
        "RETURN labels(n) AS labels, count(*) AS count",
        {"tenant_id": tenant},
    )
    node_labels: list[str] = sorted(
        {
            str(label)
            for row in rows
            for label in (row.get("labels") or [])
        }
    )
    rel_types_row = await _safe_query(
        client,
        "MATCH ()-[r]->() WHERE r.tenant_id = $tenant_id "
        "RETURN DISTINCT type(r) AS t",
        {"tenant_id": tenant},
    )
    rel_types = sorted({str(r.get("t")) for r in rel_types_row if r.get("t")})
    return {
        "node_labels": node_labels,
        "relationship_types": rel_types,
        "tenant_id": tenant,
        "rows": rows,
    }


@router.post("/cypher")
async def cypher(
    body: CypherRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(auth)
    # Strict multi-tenant SaaS: raw Cypher cannot be safely tenant-scoped — a
    # query that RETURNs scalar/aliased properties (e.g. `RETURN n.email AS e`)
    # carries no tenant_id key and slips past `_filter_rows_by_tenant`. Refuse
    # the raw surface; the templated endpoints (schema/ego/paths/resolve) stay
    # open. Single-tenant (flag off) keeps the raw console.
    if settings.multi_tenant_strict:
        raise HTTPException(status_code=403, detail="raw_cypher_disabled_strict_mt")
    if not (body.cypher or "").strip():
        raise HTTPException(status_code=422, detail="empty_cypher")
    if _has_forbidden_clause(body.cypher):
        raise HTTPException(status_code=400, detail="forbidden_clause")
    if _is_destructive(body.cypher) and not body.params.get("_confirm_destructive"):
        raise HTTPException(
            status_code=400,
            detail="destructive_requires_confirm",
        )
    params = dict(body.params or {})
    # BUG-29 — auto-inject so user queries can rely on `$tenant_id` even if
    # they forget to pass it. Caller-provided value (if any) wins so tests
    # can simulate cross-tenant attempts.
    params.setdefault(_TENANT_PARAM, tenant)
    client = Neo4jClient()
    _t0 = time.monotonic()
    rows = await _safe_query(client, body.cypher, params)
    elapsed_ms = round((time.monotonic() - _t0) * 1000, 1)
    safe_rows = _filter_rows_by_tenant(rows, tenant)
    return {
        "rows": safe_rows,
        "elapsed_ms": elapsed_ms,
        "tenant_id": tenant,
        "filtered_out": len(rows) - len(safe_rows),
    }


@router.post("/ingest")
async def ingest(
    body: IngestRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(auth)
    client = Neo4jClient()
    n_e = 0
    n_r = 0
    for e in body.entities:
        props = dict(e.get("props") or {})
        props.setdefault("tenant_id", tenant)
        await client.upsert_entity(e["label"], props, e.get("key", "id"))
        n_e += 1
    for r in body.relations:
        rel_props = dict(r.get("props") or {})
        rel_props.setdefault("tenant_id", tenant)
        await client.upsert_relation(
            r["src_id"], r["type"], r["dst_id"], rel_props
        )
        n_r += 1
    return {"entities": n_e, "relations": n_r, "tenant_id": tenant}


@router.post("/seed")
async def seed(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    """BUG-29 — admin-triggered demo graph seed for the caller's tenant.

    Idempotent (MERGE-based) so the panel "Reseed" button is safe to spam.
    """
    tenant = _resolve_tenant(auth)
    if "admin" not in (auth.roles or []):
        raise HTTPException(403, "admin_role_required")
    try:
        counts = await ensure_tenant_seed(tenant)
    except ServiceUnavailable as exc:
        logger.warning("neo4j_seed_unavailable tenant=%s err=%s", tenant, exc)
        raise HTTPException(503, "neo4j_unavailable") from exc
    return {"tenant_id": tenant, "counts": counts}


def _extract_json_obj(text: str) -> str:
    """Best-effort extraction of a JSON object from an LLM response that may be
    wrapped in a ```json … ``` fence and/or surrounded by prose. Free-tier
    models are less strict about JSON-only output, so we (1) strip a markdown
    fence, then (2) fall back to the first balanced {…} block. The caller still
    runs json.loads on the result."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    if s.startswith("{"):
        return s
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        return s[i : j + 1]
    return s


@router.post("/nl-query")
async def nl_query(
    body: NLQueryRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(auth)
    # Strict multi-tenant SaaS: NL→Cypher emits raw Cypher that flows through
    # the same scalar-bypassable row filter as /cypher, so refuse it too. The
    # templated graph endpoints remain the safe multi-tenant surface.
    if settings.multi_tenant_strict:
        raise HTTPException(status_code=403, detail="raw_cypher_disabled_strict_mt")
    if not (body.intent or "").strip():
        raise HTTPException(status_code=422, detail="empty_intent")
    # Lazy-import the cascade stack to keep the router importable on minimal
    # deployments. When the provider stack is absent OR no key is configured we
    # degrade to 422 so the client can route the NL through an external
    # translator (or POST a hand-written cypher to /v1/graph/cypher).
    try:
        from app.cascade.orchestrator import call_with_cascade
        from app.providers.cascade import get_active_providers
        from app.providers.schemas import CascadeUnavailable, ProviderError
    except ImportError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "nl_translator_unavailable",
                "reason": str(exc),
                "hint": "Provide an LLM-translated cypher via POST /v1/graph/cypher.",
            },
        )
    active = get_active_providers()
    if not active:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "nl_translator_unavailable",
                "reason": "no_providers_configured",
                "hint": "Configure a provider key, or POST a cypher to /v1/graph/cypher.",
            },
        )
    prompt = (
        "Convert this natural language to a Neo4j Cypher query for tenant "
        f"'{tenant}'. Always include WHERE n.tenant_id = $tenant_id (and the "
        "same on relationships) so cross-tenant rows cannot leak. "
        "Output the raw JSON object ONLY — no markdown fences, no prose — "
        "with shape "
        "{\"cypher\": \"...\", \"params\": {...}, \"explanation\": \"...\"}. "
        "Schema hint: nodes use :Person, :Org, :Project, :Ticket; "
        "relations: WORKS_AT, OWNS, MANAGES, ASSIGNED_TO.\n\n"
        f"NL: {body.intent}\nLocale: {body.locale}"
    )
    primary, *rest = active

    def _parse(resp):
        raw = _extract_json_obj(getattr(resp, "text", "") or "")
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) and "cypher" in obj else None

    async def _call(p, cache=True):
        try:
            return await call_with_cascade(
                p, primary=primary, fallbacks=tuple(rest),
                tenant_id=tenant, use_cache=cache,
            )
        except CascadeUnavailable:
            raise  # busy, not broken — 503 + Retry-After, from the app handler
        except ProviderError as exc:
            raise HTTPException(
                502, f"nl_translation_failed: {exc.message or str(exc)}"
            ) from exc

    parsed = _parse(await _call(prompt))
    if parsed is None:
        # Free-tier model returned prose / invalid JSON — retry once with a
        # stricter instruction (cache off so we don't replay the bad answer).
        parsed = _parse(
            await _call(
                prompt + "\n\nIMPORTANT: respond with the raw JSON object ONLY.",
                cache=False,
            )
        )
    if parsed is None:
        raise HTTPException(502, "llm_returned_non_json")
    if _is_destructive(parsed["cypher"]):
        raise HTTPException(400, "destructive_nl_query_rejected")
    if _has_forbidden_clause(parsed["cypher"]):
        # An injected NL intent could coax the translator into emitting a
        # CALL apoc.load.json(...) SSRF or a LOAD CSV file read.
        raise HTTPException(400, "forbidden_clause")
    params = dict(parsed.get("params") or {})
    params.setdefault(_TENANT_PARAM, tenant)
    client = Neo4jClient()
    rows = await _safe_query(client, parsed["cypher"], params)
    safe_rows = _filter_rows_by_tenant(rows, tenant)
    return {
        "cypher": parsed["cypher"],
        "explanation": parsed.get("explanation"),
        "rows": safe_rows,
        "tenant_id": tenant,
    }
