# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agentic Growth — live HTTP smoke (real auth + routing + service + DB).

Unit tests stub the model; this exercises the actual endpoints end-to-end via
the panel cookie session, proving the API surface for the Agent Registry,
Dashboard, Approval Center, Lead Intelligence, Inbound + Knowledge screens
responds (agent runs degrade gracefully with no provider — still HTTP 200).
"""

from __future__ import annotations


def _login(client) -> None:
    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "CHANGEME"}
    )
    assert r.status_code == 200, r.text


def test_agent_registry_endpoint(client) -> None:
    _login(client)
    r = client.get("/v1/agents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 21
    assert any(c["agents"] for c in body["categories"])


def test_dashboard_endpoint(client) -> None:
    _login(client)
    r = client.get("/v1/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agents"]["total"] == 21
    assert "approvals" in body and "activity" in body


def test_lead_create_and_priority(client) -> None:
    _login(client)
    r = client.post(
        "/v1/leads", json={"company_name": "Smoke A.Ş.", "sector": "İnşaat"}
    )
    assert r.status_code == 200, r.text
    lid = r.json()["id"]
    r = client.get("/v1/leads")
    assert r.status_code == 200
    assert any(item["id"] == lid for item in r.json()["items"])


def test_approvals_endpoint(client) -> None:
    _login(client)
    r = client.get("/v1/approvals")
    assert r.status_code == 200, r.text
    assert "pending_total" in r.json()


def test_agent_run_degrades_gracefully(client) -> None:
    _login(client)
    r = client.post("/v1/agents/knowledge_base/run", json={"task": "Fiyat nedir?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body and body["agent_id"] == "knowledge_base"


def test_inbound_endpoint(client) -> None:
    _login(client)
    r = client.post("/v1/inbound", json={"message": "Fiyat öğrenebilir miyim?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "intent" in body and "draft" in body


def test_knowledge_ask_endpoint(client) -> None:
    _login(client)
    r = client.post(
        "/v1/knowledge/ask", json={"question": "Hangi hizmetleri sunuyorsunuz?"}
    )
    assert r.status_code == 200, r.text
    assert "answer" in r.json()


def test_unauthenticated_blocked(client) -> None:
    # no login → cookie/bearer absent → 401
    assert client.get("/v1/agents").status_code == 401
    assert client.get("/v1/dashboard").status_code == 401
