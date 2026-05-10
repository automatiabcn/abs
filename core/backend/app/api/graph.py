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
    """Return live schema scoped to the caller's tenant. Falls back to the
    seeded label/relationship hints if Neo4j is empty so the UI never
    renders a blank sidebar."""
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
    ) or ["Person", "Org", "Project", "Ticket"]
    # Read relationship types via a real lookup; fall back to the seed types
    # so the UI sidebar still shows something on a fresh boot.
    rel_types_row = await _safe_query(
        client,
        "MATCH ()-[r]->() WHERE r.tenant_id = $tenant_id "
        "RETURN DISTINCT type(r) AS t",
        {"tenant_id": tenant},
    )
    rel_types = sorted({str(r.get("t")) for r in rel_types_row if r.get("t")}) or [
        "WORKS_AT",
        "OWNS",
        "MANAGES",
        "ASSIGNED_TO",
    ]
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
    rows = await _safe_query(client, body.cypher, params)
    safe_rows = _filter_rows_by_tenant(rows, tenant)
    return {
        "rows": safe_rows,
        "elapsed_ms": 0.0,
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


@router.post("/nl-query")
async def nl_query(
    body: NLQueryRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(auth)
    # Lazy-import cascade to keep router importable without provider stack.
    # Some Q7 deployments ship without `cascade_call`; degrade to 422 so the
    # client can route the NL through an external translator instead of 503.
    try:
        from app.providers.cascade import cascade_call  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "nl_translator_unavailable",
                "reason": str(exc),
                "hint": "Provide an LLM-translated cypher via POST /v1/graph/cypher.",
            },
        )
    prompt = (
        "Convert this natural language to a Neo4j Cypher query for tenant "
        f"'{tenant}'. Always include WHERE n.tenant_id = $tenant_id (and the "
        "same on relationships) so cross-tenant rows cannot leak. "
        "Return JSON ONLY with shape "
        "{\"cypher\": \"...\", \"params\": {...}, \"explanation\": \"...\"}. "
        "Schema hint: nodes use :Person, :Org, :Project, :Ticket; "
        "relations: WORKS_AT, OWNS, MANAGES, ASSIGNED_TO.\n\n"
        f"NL: {body.intent}\nLocale: {body.locale}"
    )
    response = await cascade_call(prompt=prompt)
    completion = response.get("completion") or response.get("text") or "{}"
    try:
        parsed = json.loads(completion)
    except json.JSONDecodeError:
        raise HTTPException(502, "llm_returned_non_json")
    if "cypher" not in parsed:
        raise HTTPException(502, "llm_returned_no_cypher")
    if _is_destructive(parsed["cypher"]):
        raise HTTPException(400, "destructive_nl_query_rejected")
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
