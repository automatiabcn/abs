"""BUG-V2 — Workflow execute response carries USD cost estimate.

PROMISE.md vow:
  "Estimated cost per run: $X.XX shows zero for free-tier-only
   workflows."

Pinning two contracts:
  1. A workflow whose nodes name only free providers
     (groq / cloudflare / gemini / cohere / ollama / local) returns
     `estimated_cost_usd == 0.0`.
  2. A workflow with at least one anthropic-tagged node returns
     `estimated_cost_usd > 0`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    for payload in (
        {"email": "admin@local", "password": "CHANGEME"},
        {"email": "admin@demo-acme.com", "password": "DemoPass2026!"},
    ):
        if client.post("/auth/login", json=payload).status_code == 200:
            return
    pytest.skip("BUG-V2: no bootstrap admin available")


def _execute(client: TestClient, workflow: dict) -> dict:
    r = client.post(
        "/v1/workflows/execute",
        json={"workflow": workflow, "dry_run": True},
    )
    assert r.status_code == 200, (r.status_code, r.text[:300])
    body = r.json()
    assert "estimated_cost_usd" in body, (
        "BUG-V2 contract: response must surface estimated_cost_usd"
    )
    return body


def test_promise_v2_free_only_workflow_returns_zero_cost(
    client: TestClient,
):
    _login(client)
    workflow = {
        "nodes": [
            {
                "id": "trigger",
                "kind": "trigger",
                "name": "Manual run",
                "config": {},
            },
            {
                "id": "llm-1",
                "kind": "llm_call",
                "name": "Groq summary",
                "config": {"provider": "groq", "model": "gpt-oss-120b"},
            },
            {
                "id": "llm-2",
                "kind": "llm_call",
                "name": "Gemini polish",
                "config": {"provider": "gemini", "model": "gemini-2.5-flash"},
            },
            {
                "id": "out",
                "kind": "output",
                "name": "Output",
                "config": {},
            },
        ],
        "edges": [
            {"source": "trigger", "target": "llm-1"},
            {"source": "llm-1", "target": "llm-2"},
            {"source": "llm-2", "target": "out"},
        ],
    }
    body = _execute(client, workflow)
    assert body["estimated_cost_usd"] == 0.0, body


def test_promise_v2_anthropic_node_returns_nonzero_cost(
    client: TestClient,
):
    _login(client)
    workflow = {
        "nodes": [
            {
                "id": "trigger",
                "kind": "trigger",
                "name": "Manual run",
                "config": {},
            },
            {
                "id": "claude",
                "kind": "llm_call",
                "name": "Claude summarize",
                "config": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                },
            },
        ],
        "edges": [{"source": "trigger", "target": "claude"}],
    }
    body = _execute(client, workflow)
    assert body["estimated_cost_usd"] > 0.0, body
    # Sanity-check the surface the panel renders.
    assert isinstance(body["estimated_cost_usd"], float)
    assert "steps" in body
