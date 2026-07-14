# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""`/admin/graph` Cypher returned HTTP 500 because the customer
compose had no Neo4j service and the legacy `/v1/graph/cypher` handler
let the bolt driver's `ServiceUnavailable` bubble up untranslated.

Behaviour:
* Neo4j 5.20-community ships in `infra/docker-compose.customer.yml`.
* `app/integrations/neo4j_seed.py` plants Person/Org/Project/Ticket nodes
  with a `tenant_id` property so the panel renders rows on first boot.
* `app/api/graph.py` flips auth to `get_admin_or_bearer_auth_context`,
  injects `$tenant_id` into every Cypher, and post-filters returned rows
  to drop any cross-tenant leakage.
* Bolt driver outages now return HTTP 503 with `neo4j_unavailable`.

These tests guard the policy without booting Neo4j (driver calls are stubbed).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import graph as graph_routes
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.integrations import neo4j_seed
from app.main import app


@pytest.fixture()
def admin_ctx():
    """Tenant-A admin AuthContext used for most tests."""
    return AuthContext(
        subject="admin@acme.local",
        tenant_id="tenant-a",
        roles=["admin"],
        raw_claims={"sub": "admin@acme.local"},
    )


@pytest.fixture()
def admin_client(client: TestClient, admin_ctx: AuthContext):
    app.dependency_overrides[get_admin_or_bearer_auth_context] = lambda: admin_ctx
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_admin_or_bearer_auth_context, None)


# ---------------------------------------------------------------------------
# Tenant filter post-process — the unit-testable core of the fix.
# ---------------------------------------------------------------------------
def test_filter_rows_keeps_matching_tenant() -> None:
    rows = [
        {"p": {"tenant_id": "tenant-a", "name": "Anna"}},
        {"p": {"tenant_id": "tenant-a", "name": "Bora"}},
    ]
    out = graph_routes._filter_rows_by_tenant(rows, "tenant-a")
    assert len(out) == 2


def test_filter_rows_drops_cross_tenant_leak() -> None:
    rows = [
        {"p": {"tenant_id": "tenant-a", "name": "Anna"}},
        {"p": {"tenant_id": "tenant-b", "name": "Mallory"}},
    ]
    out = graph_routes._filter_rows_by_tenant(rows, "tenant-a")
    assert len(out) == 1
    assert out[0]["p"]["name"] == "Anna"


def test_filter_rows_passes_scalar_only_rows() -> None:
    """Counts / scalar projections have no tenant_id; they should pass."""
    rows = [{"n": 42}, {"label": "Person", "count": 3}]
    out = graph_routes._filter_rows_by_tenant(rows, "tenant-a")
    assert len(out) == 2


def test_extract_tenant_walks_nested_lists() -> None:
    nested = [
        {"name": "Anna", "tenant_id": "tenant-c"},
        {"name": "Bora"},
    ]
    found = graph_routes._extract_tenant(nested)
    assert found == "tenant-c"


# ---------------------------------------------------------------------------
# Endpoint behaviour — auth / destructive guard / tenant injection / 503.
# ---------------------------------------------------------------------------
def test_cypher_destructive_blocked(admin_client: TestClient) -> None:
    """No live neo4j needed — guard rejects before client call."""
    r = admin_client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n) DETACH DELETE n", "params": {}},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "destructive_requires_confirm"


def test_cypher_auto_injects_tenant_param(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    admin_ctx: AuthContext,
) -> None:
    captured: dict[str, Any] = {}

    async def _fake_query(self, cypher: str, params: dict | None = None):
        captured["cypher"] = cypher
        captured["params"] = params or {}
        return [{"n": {"tenant_id": admin_ctx.tenant_id, "id": "p-anna"}}]

    monkeypatch.setattr(graph_routes.Neo4jClient, "query", _fake_query, raising=True)
    r = admin_client.post(
        "/v1/graph/cypher",
        json={
            "cypher": "MATCH (n:Person {tenant_id: $tenant_id}) RETURN n",
            "params": {},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == admin_ctx.tenant_id
    assert captured["params"]["tenant_id"] == admin_ctx.tenant_id
    assert body["filtered_out"] == 0
    assert len(body["rows"]) == 1


def test_cypher_post_filters_cross_tenant_rows(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    admin_ctx: AuthContext,
) -> None:
    async def _fake_query(self, cypher: str, params: dict | None = None):
        return [
            {"n": {"tenant_id": admin_ctx.tenant_id, "id": "p-anna"}},
            {"n": {"tenant_id": "tenant-b", "id": "p-mallory"}},
        ]

    monkeypatch.setattr(graph_routes.Neo4jClient, "query", _fake_query, raising=True)
    r = admin_client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n:Person) RETURN n", "params": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["n"]["id"] == "p-anna"
    assert body["filtered_out"] == 1


def test_cypher_elapsed_ms_is_measured_not_hardcoded(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    admin_ctx: AuthContext,
) -> None:
    """Regression: the handler used to return a hardcoded `elapsed_ms: 0.0`,
    so the panel always showed "0 ms" regardless of real query time. It must
    now reflect the actual wall time of the query."""
    import asyncio

    async def _slow_query(self, cypher: str, params: dict | None = None):
        await asyncio.sleep(0.02)
        return [{"n": {"tenant_id": admin_ctx.tenant_id, "id": "p-anna"}}]

    monkeypatch.setattr(graph_routes.Neo4jClient, "query", _slow_query, raising=True)
    r = admin_client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n:Person) RETURN n", "params": {}},
    )
    assert r.status_code == 200, r.text
    elapsed = r.json()["elapsed_ms"]
    assert isinstance(elapsed, (int, float))
    # The stubbed query sleeps 20ms — a real measurement must be clearly > 0.
    assert elapsed > 5, f"elapsed_ms not measured: {elapsed}"


def test_schema_empty_graph_returns_empty_not_placeholders(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the schema endpoint used to substitute hardcoded
    Person/Org/… + WORKS_AT/… labels when the tenant graph was empty, so a
    fresh (or wrong-tenant) graph looked populated. An empty graph must
    report empty label/relationship lists."""

    async def _empty(self, cypher: str, params: dict | None = None):
        return []

    monkeypatch.setattr(graph_routes.Neo4jClient, "query", _empty, raising=True)
    r = admin_client.get("/v1/graph/schema")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["node_labels"] == []
    assert body["relationship_types"] == []


def test_cypher_neo4j_unavailable_returns_503(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neo4j.exceptions import ServiceUnavailable

    async def _down(self, cypher: str, params: dict | None = None):
        raise ServiceUnavailable("bolt://neo4j:7687 unreachable")

    monkeypatch.setattr(graph_routes.Neo4jClient, "query", _down, raising=True)
    r = admin_client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n) RETURN n LIMIT 1", "params": {}},
    )
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "neo4j_unavailable"


def test_seed_endpoint_invokes_ensure_tenant_seed(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, admin_ctx
) -> None:
    captured: dict[str, str] = {}

    async def _fake_seed(tenant_id: str, *, client=None):
        captured["tenant_id"] = tenant_id
        return {"Person": 3, "Org": 2}

    monkeypatch.setattr(graph_routes, "ensure_tenant_seed", _fake_seed)
    r = admin_client.post("/v1/graph/seed", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == admin_ctx.tenant_id
    assert body["counts"]["Person"] == 3
    assert captured["tenant_id"] == admin_ctx.tenant_id


def test_seed_endpoint_requires_admin(client: TestClient) -> None:
    member = AuthContext(
        subject="member@local",
        tenant_id="tenant-a",
        roles=["member"],
        raw_claims={"sub": "member@local"},
    )
    app.dependency_overrides[get_admin_or_bearer_auth_context] = lambda: member
    try:
        r = client.post("/v1/graph/seed", json={})
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "admin_role_required"
    finally:
        app.dependency_overrides.pop(get_admin_or_bearer_auth_context, None)


# ---------------------------------------------------------------------------
# Seed module — idempotency contract.
# ---------------------------------------------------------------------------
async def test_ensure_tenant_seed_calls_merge_for_each_node_and_edge() -> None:
    """The seed must MERGE every Person/Org/Project/Ticket + 4 edges. We
    don't need a real Neo4j; an AsyncMock counts the calls."""
    fake_client = AsyncMock()
    out = await neo4j_seed.ensure_tenant_seed("tenant-a", client=fake_client)
    # 3 People + 2 Orgs + 2 Projects + 2 Tickets + 3 WORKS_AT
    # + 2 OWNS + 2 MANAGES + 2 ASSIGNED_TO = 18 MERGE calls.
    assert fake_client.query.call_count == 18
    assert out["Person"] == 3
    assert out["Org"] == 2
    assert out["MANAGES"] == 2


async def test_ensure_tenant_seed_rejects_blank_tenant() -> None:
    with pytest.raises(ValueError):
        await neo4j_seed.ensure_tenant_seed("   ")
