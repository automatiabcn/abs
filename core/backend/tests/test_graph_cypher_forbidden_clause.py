# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Graph round — /v1/graph/cypher must reject stored-procedure / data-loading
clauses that escape "tenant-scoped graph query".

The _DESTRUCTIVE blocklist (DELETE/CREATE/MERGE/...) misses CALL, LOAD CSV and
FOREACH. On a raw-Cypher endpoint those are an SSRF primitive
(CALL apoc.load.json('http://169.254.169.254/...')), a local file read
(LOAD CSV FROM 'file:///etc/passwd'), Neo4j info-disclosure
(CALL dbms.listConfig()) and an APOC-based destructive path the blocklist
can't see. None are used anywhere in the app, so they are hard-blocked (no
_confirm_destructive bypass) on both /cypher and /nl-query.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import graph as graph_routes
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.main import app


@pytest.fixture()
def admin_ctx():
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


@pytest.mark.parametrize(
    "cypher",
    [
        "CALL dbms.listConfig()",
        "CALL apoc.load.json('http://169.254.169.254/latest/meta-data/')",
        "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row",
        "MATCH (n) FOREACH (x IN [1] | SET n.p = 1) RETURN n",
        "USING PERIODIC COMMIT 500 LOAD CSV FROM 'http://x/y' AS r RETURN r",
        "match (n) call apoc.create.node(['X'],{}) yield node return node",  # lowercase
    ],
)
def test_cypher_forbidden_clause_blocked(admin_client: TestClient, cypher: str) -> None:
    """Rejected with 400 before any Neo4j call — no live driver needed."""
    r = admin_client.post("/v1/graph/cypher", json={"cypher": cypher, "params": {}})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "forbidden_clause"


def test_confirm_destructive_cannot_bypass_forbidden_clause(
    admin_client: TestClient,
) -> None:
    """The destructive-confirm escape hatch must NOT open a CALL/SSRF path."""
    r = admin_client.post(
        "/v1/graph/cypher",
        json={
            "cypher": "CALL apoc.load.json('http://evil/')",
            "params": {"_confirm_destructive": True},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "forbidden_clause"


@pytest.mark.parametrize(
    "cypher",
    [
        'LOAD /*x*/ CSV FROM "file:///etc/passwd" AS r RETURN r',  # block-comment split
        "LOAD // sneaky\n CSV FROM 'x' AS r RETURN r",  # line-comment split
        "USING/**/PERIODIC/**/COMMIT 500 LOAD/**/CSV FROM 'x' AS r RETURN r",
        "CA/**/LL",  # cannot split a single token, but ensure no crash
    ],
)
def test_comment_split_clause_not_bypassable(
    admin_client: TestClient, cypher: str
) -> None:
    """Cypher comments between multi-word clause keywords must NOT slip past the
    forbidden-clause guard (the parser ignores the comment and executes LOAD CSV)."""
    # The first three are real LOAD CSV / PERIODIC COMMIT bypasses → must 400.
    blocked = "LOAD" in cypher.upper() or "PERIODIC" in cypher.upper()
    r = admin_client.post("/v1/graph/cypher", json={"cypher": cypher, "params": {}})
    if blocked:
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "forbidden_clause"


def test_helper_no_false_positive_on_property_substrings() -> None:
    """Word-boundary matching: 'RECALL'/'FORECASTING' as data must NOT trip."""
    assert graph_routes._has_forbidden_clause("CALL db.labels()") is True
    assert graph_routes._has_forbidden_clause("LOAD CSV FROM 'x' AS r RETURN r") is True
    assert (
        graph_routes._has_forbidden_clause(
            "MATCH (n) WHERE n.note = 'RECALL the FORECASTING' RETURN n"
        )
        is False
    )
    assert (
        graph_routes._has_forbidden_clause(
            "MATCH (n:Person {tenant_id: $tenant_id}) RETURN n"
        )
        is False
    )
