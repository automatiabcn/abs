"""Q7 Phase A — Neo4j integration tests.

Live tests are skipped unless ABS_NEO4J_LIVE=1 (CI default = skip).
The destructive-guard test runs without Neo4j — FastAPI rejects before
the client is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

LIVE = os.environ.get("ABS_NEO4J_LIVE") == "1"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "graph_seed.json"


def _override_admin(client):
    """Bypass cookie auth — pretend we're a logged-in admin."""
    from app.api.auth import current_admin
    from app.main import app

    app.dependency_overrides[current_admin] = lambda: {"sub": "test-admin@local"}
    yield
    app.dependency_overrides.pop(current_admin, None)


@pytest.fixture()
def admin_client(client):
    from app.api.auth import current_admin
    from app.main import app

    app.dependency_overrides[current_admin] = lambda: {"sub": "test-admin@local"}
    try:
        yield client
    finally:
        app.dependency_overrides.pop(current_admin, None)


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
    """Monkeypatch cascade_call → fixed Cypher response; verify pass-through."""
    import app.providers.cascade as cascade_mod

    async def _fake_cascade_call(prompt: str, **_):
        return {
            "completion": json.dumps(
                {
                    "cypher": (
                        "MATCH (p:Person)-[:WORKS_AT]->"
                        "(c:Company {name: \"DemoCo\"}) RETURN p"
                    ),
                    "params": {},
                }
            )
        }

    monkeypatch.setattr(
        cascade_mod, "cascade_call", _fake_cascade_call, raising=False
    )

    r = admin_client.post(
        "/v1/graph/nl-query",
        json={"intent": "DemoCo'da kim çalışıyor?", "locale": "tr"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "cypher" in body
    assert len(body["data"]) == 2
