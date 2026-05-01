"""Q7 Phase A — /v1/graph router (Cypher, ingest, NL query, schema, health)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import current_admin
from app.integrations.neo4j_client import Neo4jClient

router = APIRouter(prefix="/v1/graph", tags=["graph"])
logger = logging.getLogger(__name__)

_DESTRUCTIVE = ("DELETE", "DROP", "REMOVE", "DETACH DELETE")


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


@router.get("/health")
async def health(_admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    client = Neo4jClient()
    ok = await client.health()
    return {"ok": ok, "uri": "bolt://neo4j:7687"}


@router.get("/schema")
async def schema(_admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    client = Neo4jClient()
    rows = await client.query(
        "MATCH (n) RETURN labels(n) AS labels, count(*) AS count"
    )
    return {"labels": rows}


@router.post("/cypher")
async def cypher(
    body: CypherRequest, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    if _is_destructive(body.cypher) and not body.params.get("_confirm_destructive"):
        raise HTTPException(
            status_code=400,
            detail="destructive_requires_confirm",
        )
    client = Neo4jClient()
    return {"data": await client.query(body.cypher, body.params)}


@router.post("/ingest")
async def ingest(
    body: IngestRequest, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    client = Neo4jClient()
    n_e = 0
    n_r = 0
    for e in body.entities:
        await client.upsert_entity(e["label"], e["props"], e.get("key", "id"))
        n_e += 1
    for r in body.relations:
        await client.upsert_relation(
            r["src_id"], r["type"], r["dst_id"], r.get("props")
        )
        n_r += 1
    return {"entities": n_e, "relations": n_r}


@router.post("/nl-query")
async def nl_query(
    body: NLQueryRequest, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
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
        "Convert this natural language to a Neo4j Cypher query. "
        "Return JSON ONLY with shape "
        "{\"cypher\": \"...\", \"params\": {...}, \"explanation\": \"...\"}. "
        "Schema hint: nodes use :Person, :Company, :Document; "
        "relations: WORKS_AT, MENTIONS, OWNS, MANAGES.\n\n"
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
    client = Neo4jClient()
    data = await client.query(parsed["cypher"], parsed.get("params", {}))
    return {
        "cypher": parsed["cypher"],
        "explanation": parsed.get("explanation"),
        "data": data,
    }
