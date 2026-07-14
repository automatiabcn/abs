"""Q7 Phase A — Neo4j integration tests.

Live tests are skipped unless ABS_NEO4J_LIVE=1 (CI default = skip).
The destructive-guard test runs without Neo4j — FastAPI rejects before
the client is touched.

graph routes flipped from `current_admin` (cookie-only dict) to
`get_admin_or_bearer_auth_context` (AuthContext with tenant_id). The
fixture now overrides the new dep so the test fleet keeps passing without
booting an actual Neo4j.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

LIVE = os.environ.get("ABS_NEO4J_LIVE") == "1"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "graph_seed.json"


def _fake_auth():
    from app.api.v1.deps import AuthContext

    return AuthContext(
        subject="test-admin@local",
        tenant_id="test-tenant",
        roles=["admin"],
        raw_claims={"sub": "test-admin@local"},
    )


@pytest.fixture()
def admin_client(client):
    from app.api.v1.deps import get_admin_or_bearer_auth_context
    from app.main import app

    app.dependency_overrides[get_admin_or_bearer_auth_context] = _fake_auth
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_admin_or_bearer_auth_context, None)


def test_cypher_destructive_blocked(admin_client):
    """No live neo4j needed — guard rejects before client call."""
    r = admin_client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n) DETACH DELETE n", "params": {}},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "destructive_requires_confirm"


@pytest.mark.skipif(not LIVE, reason="ABS_NEO4J_LIVE!=1 — skipping live Neo4j test")
def test_cypher_destructive_with_confirm(admin_client):
    """Same destructive query with explicit confirm flag should pass guard."""
    r = admin_client.post(
        "/v1/graph/cypher",
        json={
            "cypher": "MATCH (n:Person {id: 'unlikely-id-zzz'}) DETACH DELETE n",
            "params": {"_confirm_destructive": True},
        },
    )
    assert r.status_code == 200, r.text
    assert "data" in r.json()


@pytest.mark.skipif(not LIVE, reason="ABS_NEO4J_LIVE!=1 — skipping live Neo4j test")
def test_ingest_seed_then_count(admin_client):
    """Seed graph, then verify two people work at DemoCo."""
    seed = json.loads(FIXTURE_PATH.read_text())
    r = admin_client.post("/v1/graph/ingest", json=seed)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entities"] == 3
    assert body["relations"] == 3

    r = admin_client.post(
        "/v1/graph/cypher",
        json={
            "cypher": (
                "MATCH (p:Person)-[:WORKS_AT]->"
                "(c:Company {name: 'DemoCo'}) RETURN count(p) AS n"
            ),
            "params": {},
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows[0]["n"] == 2


@pytest.mark.skipif(not LIVE, reason="ABS_NEO4J_LIVE!=1 — skipping live Neo4j test")
def test_health_endpoint(admin_client):
    r = admin_client.get("/v1/graph/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["uri"].startswith("bolt://")


@pytest.mark.skipif(not LIVE, reason="ABS_NEO4J_LIVE!=1 — skipping live Neo4j test")
def test_nl_query_mocked(admin_client, monkeypatch):
    """Monkeypatch the cascade → fixed Cypher response; verify pass-through.

    nl-query routes through `call_with_cascade` (orchestrator) + the active
    provider chain, then returns `{cypher, explanation, rows, tenant_id}`.
    """
    import app.cascade.orchestrator as orch_mod
    import app.providers.cascade as cascade_mod
    from app.providers.schemas import ProviderResponse

    monkeypatch.setattr(
        cascade_mod, "get_active_providers", lambda *a, **k: ["groq"], raising=False
    )

    async def _fake_call_with_cascade(prompt, *, primary=None, **_):
        return ProviderResponse(
            text=json.dumps(
                {
                    "cypher": (
                        "MATCH (p:Person)-[:WORKS_AT]->"
                        '(c:Org {name: "DemoCo"}) RETURN p'
                    ),
                    "params": {},
                    "explanation": "stub",
                }
            ),
            provider="groq",
            model="stub",
        )

    monkeypatch.setattr(
        orch_mod, "call_with_cascade", _fake_call_with_cascade, raising=False
    )

    r = admin_client.post(
        "/v1/graph/nl-query",
        json={"intent": "DemoCo'da kim çalışıyor?", "locale": "tr"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "cypher" in body
    assert "rows" in body
