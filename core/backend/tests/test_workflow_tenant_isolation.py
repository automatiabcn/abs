"""Cross-tenant isolation for workflow jobs.

A job is owned by the admin identity that enqueued it. Another tenant's admin
must not be able to read its status (which may carry RAG hits / API responses
/ LLM output in node_outputs) nor — worse — approve/reject its hitl gate. The
endpoints answer 404 (not 403) on a foreign job so existence isn't disclosed.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.workflow_v10.runner as runner
from app.api.workflows import _job_owner_matches


def _login(client: TestClient) -> None:
    for payload in (
        {"email": "admin@local", "password": "CHANGEME"},
        {"email": "admin@demo-acme.com", "password": "DemoPass2026!"},
    ):
        if client.post("/auth/login", json=payload).status_code == 200:
            return
    pytest.skip("no bootstrap admin available")


def test_owner_match_helper():
    assert _job_owner_matches({"tenant_slug": "alice"}, {"sub": "alice"}) is True
    assert _job_owner_matches({"tenant_slug": "alice"}, {"sub": "bob"}) is False
    # no sub → "default" key (single-tenant/dev backwards-compat)
    assert _job_owner_matches({"tenant_slug": "default"}, {}) is True


def test_cross_tenant_status_is_404(client: TestClient):
    _login(client)
    job_id = asyncio.new_event_loop().run_until_complete(
        runner.enqueue(
            {"nodes": [{"id": "g", "kind": "hitl", "config": {}}], "edges": []},
            "other-tenant-xyz",
        )
    )
    r = client.get(f"/v1/workflows/jobs/{job_id}")
    assert r.status_code == 404, r.text[:200]


def test_cross_tenant_resume_is_404(client: TestClient):
    _login(client)
    job_id = asyncio.new_event_loop().run_until_complete(
        runner.enqueue(
            {"nodes": [{"id": "g", "kind": "hitl", "config": {}}], "edges": []},
            "other-tenant-xyz",
        )
    )
    r = client.post(f"/v1/workflows/jobs/{job_id}/resume", json={"approved": True})
    assert r.status_code == 404, r.text[:200]
    # and the foreign job must remain un-resumed (not approved by the intruder)
    st = runner.status(job_id)
    assert st["node_outputs"].get("g", {}).get("approved") is not True


def test_own_job_is_accessible(client: TestClient):
    _login(client)
    r = client.post(
        "/v1/workflows/execute",
        json={
            "workflow": {
                "nodes": [
                    {"id": "o", "kind": "output", "config": {"output_template": "x"}}
                ],
                "edges": [],
            },
            "dry_run": False,
        },
    )
    job_id = r.json()["job_id"]
    rs = client.get(f"/v1/workflows/jobs/{job_id}")
    assert rs.status_code == 200  # owner can read their own job
