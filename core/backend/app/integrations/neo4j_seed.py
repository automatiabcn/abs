# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Neo4j tenant init seed.

`/admin/graph` is empty on a fresh customer install, which historically caused
`MATCH (p:Person) ...` to return no rows (looked like the whole stack was
broken). This module ships a tiny demo graph (Person/Org/Project/Ticket nodes
+ WORKS_AT/OWNS/MANAGES/ASSIGNED_TO edges) tagged with the tenant id so:

* the operator UI shows real schema labels + sample rows immediately,
* every node carries a `tenant_id` property so cross-tenant queries return
  zero rows when the new graph router post-filter runs.

The seed is idempotent: re-running it is a MERGE that doesn't create
duplicates. Lifespan calls `ensure_tenant_seed("default")` so the panel is
usable on first boot; the admin can re-trigger it per tenant via
`POST /v1/graph/seed`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.integrations.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

__all__ = ["ensure_tenant_seed", "tenant_node_counts"]


_SEED_PEOPLE: list[dict[str, str]] = [
    {"id": "p-anna", "name": "Anna Kaya", "email": "anna@acme.local", "role": "CTO"},
    {
        "id": "p-bora",
        "name": "Bora Aksoy",
        "email": "bora@acme.local",
        "role": "Eng Lead",
    },
    {"id": "p-cem", "name": "Cem Demir", "email": "cem@acme.local", "role": "Engineer"},
]

_SEED_ORGS: list[dict[str, str]] = [
    {"id": "o-acme", "name": "Acme", "industry": "saas"},
    {"id": "o-foundry", "name": "Foundry", "industry": "consulting"},
]

_SEED_PROJECTS: list[dict[str, str]] = [
    {"id": "pr-onboarding", "name": "Customer Onboarding", "status": "active"},
    {"id": "pr-billing", "name": "Billing Revamp", "status": "planning"},
]

_SEED_TICKETS: list[dict[str, str]] = [
    {"id": "t-101", "title": "Stripe webhook idempotency", "severity": "P1"},
    {"id": "t-102", "title": "Cerbos pre-warm latency spike", "severity": "P2"},
]

_SEED_WORKS_AT: list[tuple[str, str]] = [
    ("p-anna", "o-acme"),
    ("p-bora", "o-acme"),
    ("p-cem", "o-foundry"),
]

_SEED_MANAGES: list[tuple[str, str]] = [
    ("p-anna", "pr-onboarding"),
    ("p-bora", "pr-billing"),
]

_SEED_ASSIGNED_TO: list[tuple[str, str]] = [
    ("p-bora", "t-101"),
    ("p-cem", "t-102"),
]

_SEED_OWNS: list[tuple[str, str]] = [
    ("o-acme", "pr-onboarding"),
    ("o-acme", "pr-billing"),
]


async def ensure_tenant_seed(
    tenant_id: str,
    *,
    client: Neo4jClient | None = None,
) -> dict[str, int]:
    """Idempotently MERGE the demo subgraph for *tenant_id*.

    Returns a `{label: count}` summary so the caller can log it. Each MERGE
    keys on `(label, tenant_id, id)` so re-runs are no-ops.
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_id must be a non-empty string")
    cli = client or Neo4jClient()
    out: dict[str, int] = {
        "Person": 0,
        "Org": 0,
        "Project": 0,
        "Ticket": 0,
        "WORKS_AT": 0,
        "OWNS": 0,
        "MANAGES": 0,
        "ASSIGNED_TO": 0,
    }

    async def _merge_nodes(label: str, rows: list[dict[str, str]]) -> None:
        for row in rows:
            cypher = (
                f"MERGE (n:{label} {{tenant_id: $tenant_id, id: $id}}) "
                "SET n += $props "
                "RETURN n"
            )
            await cli.query(
                cypher,
                {"tenant_id": tenant_id, "id": row["id"], "props": dict(row)},
            )
            out[label] += 1

    await _merge_nodes("Person", _SEED_PEOPLE)
    await _merge_nodes("Org", _SEED_ORGS)
    await _merge_nodes("Project", _SEED_PROJECTS)
    await _merge_nodes("Ticket", _SEED_TICKETS)

    async def _merge_edges(rel: str, pairs: list[tuple[str, str]]) -> None:
        for src, dst in pairs:
            cypher = (
                "MATCH (a {tenant_id: $tenant_id, id: $src}), "
                "(b {tenant_id: $tenant_id, id: $dst}) "
                f"MERGE (a)-[r:{rel} {{tenant_id: $tenant_id}}]->(b) "
                "RETURN r"
            )
            await cli.query(
                cypher,
                {"tenant_id": tenant_id, "src": src, "dst": dst},
            )
            out[rel] += 1

    await _merge_edges("WORKS_AT", _SEED_WORKS_AT)
    await _merge_edges("OWNS", _SEED_OWNS)
    await _merge_edges("MANAGES", _SEED_MANAGES)
    await _merge_edges("ASSIGNED_TO", _SEED_ASSIGNED_TO)

    logger.info("neo4j_tenant_seed tenant=%s counts=%s", tenant_id, out)
    return out


async def tenant_node_counts(
    tenant_id: str,
    *,
    client: Neo4jClient | None = None,
) -> dict[str, int]:
    """Return `{label: count}` for nodes carrying *tenant_id*. Used by tests
    to assert idempotency."""
    cli = client or Neo4jClient()
    rows = await cli.query(
        "MATCH (n) WHERE n.tenant_id = $tenant_id "
        "RETURN labels(n) AS labels, count(*) AS c",
        {"tenant_id": tenant_id},
    )
    out: dict[str, int] = {}
    for row in rows:
        labels: list[Any] = list(row.get("labels") or [])
        if not labels:
            continue
        out[str(labels[0])] = int(row.get("c") or 0)
    return out
