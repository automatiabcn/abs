# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GraphRAG Neo4j store — tenant-scoped, idempotent MERGE of the extracted graph.

Node labels: `GraphEntity`, `GraphChunk`. Every node + relationship carries a
`tenant_id` property so the existing graph tenant-isolation post-filter applies
and a project/tenant can never read another's subgraph (Neo4j Community = single
DB → property scoping, NOT separate databases).

We use ONE relationship type `REL` with a `type` property (e.g. WORKS_AT) rather
than dynamic relationship labels: Cypher can't parametrize a relationship type
and APOC is hard-blocked by the cypher guard, so a property keeps writes safe
and the label set bounded. `MENTIONED_IN` links an entity to its source chunk
for provenance + 1-hop retrieval.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.graph_rag.extract import ExtractionResult

logger = logging.getLogger(__name__)


# MERGE keyed on (id, tenant_id): the same logical entity id may exist for
# multiple tenants, each isolated by the tenant_id property.
_UPSERT_ENTITIES_AND_MENTIONS = """
MERGE (c:GraphChunk {id: $chunk_id, tenant_id: $tenant_id})
  SET c.doc_id = $doc_id,
      c.seq = $seq,
      c.created_at = coalesce(c.created_at, $now)
WITH c
UNWIND $entities AS ent
  MERGE (e:GraphEntity {id: ent.id, tenant_id: $tenant_id})
    SET e.name = ent.name,
        e.type = ent.type,
        e.created_at = coalesce(e.created_at, $now)
  MERGE (e)-[m:MENTIONED_IN {tenant_id: $tenant_id}]->(c)
    SET m.created_at = coalesce(m.created_at, $now)
RETURN count(e) AS entities
"""

_UPSERT_RELATIONS = """
UNWIND $relations AS rel
  MATCH (a:GraphEntity {id: rel.source_id, tenant_id: $tenant_id})
  MATCH (b:GraphEntity {id: rel.target_id, tenant_id: $tenant_id})
  MERGE (a)-[r:REL {type: rel.type, tenant_id: $tenant_id}]->(b)
    SET r.doc_id = $doc_id,
        r.created_at = coalesce(r.created_at, $now)
RETURN count(r) AS relations
"""

# Rebuild support: drop a document's chunks + the relations it sourced, then
# clean up entities that no longer appear in any chunk for this tenant.
_PURGE_DOC = """
MATCH (c:GraphChunk {doc_id: $doc_id, tenant_id: $tenant_id})
DETACH DELETE c
"""

_PURGE_DOC_RELATIONS = """
MATCH (:GraphEntity {tenant_id: $tenant_id})
      -[r:REL {doc_id: $doc_id, tenant_id: $tenant_id}]->
      (:GraphEntity {tenant_id: $tenant_id})
DELETE r
"""

_PURGE_ORPHAN_ENTITIES = """
MATCH (e:GraphEntity {tenant_id: $tenant_id})
WHERE NOT (e)-[:MENTIONED_IN]->(:GraphChunk)
DETACH DELETE e
"""


def _entities_payload(result: ExtractionResult) -> list[dict[str, str]]:
    return [{"id": e.id, "name": e.name, "type": e.type} for e in result.entities]


def _relations_payload(result: ExtractionResult) -> list[dict[str, str]]:
    return [
        {"source_id": r.source_id, "target_id": r.target_id, "type": r.type}
        for r in result.relations
    ]


async def store_chunk_graph(
    client: Any,
    *,
    tenant_id: str,
    doc_id: str,
    chunk_id: str,
    seq: int,
    result: ExtractionResult,
) -> dict[str, int]:
    """MERGE one chunk's extracted entities + relations into Neo4j.

    Idempotent: re-running with the same chunk_id/entity ids updates in place.
    Returns {"entities": n, "relations": m}.
    """
    tenant = (tenant_id or "").strip()
    if not tenant:
        raise ValueError("tenant_id is required for graph store")
    if not (chunk_id or "").strip():
        raise ValueError("chunk_id is required for graph store")
    if result.is_empty:
        # Still MERGE the chunk node so provenance/retrieval can find it.
        await client.query(
            "MERGE (c:GraphChunk {id: $chunk_id, tenant_id: $tenant_id}) "
            "SET c.doc_id = $doc_id, c.seq = $seq, "
            "c.created_at = coalesce(c.created_at, $now)",
            {
                "chunk_id": chunk_id,
                "tenant_id": tenant,
                "doc_id": doc_id,
                "seq": seq,
                "now": int(time.time()),
            },
        )
        return {"entities": 0, "relations": 0}

    now = int(time.time())
    base = {
        "chunk_id": chunk_id,
        "tenant_id": tenant,
        "doc_id": doc_id,
        "seq": seq,
        "now": now,
    }
    ent_rows = await client.query(
        _UPSERT_ENTITIES_AND_MENTIONS,
        {**base, "entities": _entities_payload(result)},
    )
    n_entities = int(ent_rows[0]["entities"]) if ent_rows else 0

    n_relations = 0
    rel_payload = _relations_payload(result)
    if rel_payload:
        rel_rows = await client.query(
            _UPSERT_RELATIONS,
            {**base, "relations": rel_payload},
        )
        n_relations = int(rel_rows[0]["relations"]) if rel_rows else 0

    return {"entities": n_entities, "relations": n_relations}


async def purge_doc_graph(client: Any, *, tenant_id: str, doc_id: str) -> None:
    """Remove a document's chunks/relations + now-orphan entities (rebuild)."""
    tenant = (tenant_id or "").strip()
    if not tenant or not (doc_id or "").strip():
        raise ValueError("tenant_id and doc_id are required to purge")
    params = {"tenant_id": tenant, "doc_id": doc_id}
    await client.query(_PURGE_DOC_RELATIONS, params)
    await client.query(_PURGE_DOC, params)
    await client.query(_PURGE_ORPHAN_ENTITIES, {"tenant_id": tenant})
