"""End-to-end HTTP test: workflow execute → hitl pause → resume → done.

Exercises the real API surface (auth cookie + ExecuteRequest + the new
POST /v1/workflows/jobs/{id}/resume) rather than the runner in isolation,
proving the hitl pause/resume path is wired through FastAPI.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    for payload in (
        {"email": "admin@local", "password": "CHANGEME"},
        {"email": "admin@demo-acme.com", "password": "DemoPass2026!"},
    ):
        if client.post("/auth/login", json=payload).status_code == 200:
            return
    pytest.skip("no bootstrap admin available")


_HITL_WF = {
    "nodes": [
        {"id": "t", "kind": "trigger", "config": {"input": "ship it"}},
        {"id": "gate", "kind": "hitl", "config": {"approval_role": "admin"}},
        {
            "id": "act",
            "kind": "output",
            "config": {"output_template": "shipped: {{t}}"},
        },
    ],
    "edges": [{"source": "t", "target": "gate"}, {"source": "gate", "target": "act"}],
}


def _poll(client: TestClient, job_id: str, want: set[str], tries: int = 50) -> dict:
    for _ in range(tries):
        r = client.get(f"/v1/workflows/jobs/{job_id}")
        assert r.status_code == 200, r.text[:300]
        st = r.json()
        if st["state"] in want:
            return st
        time.sleep(0.02)
    return st


def test_execute_pause_resume_via_http(client: TestClient):
    _login(client)
    r = client.post(
        "/v1/workflows/execute", json={"workflow": _HITL_WF, "dry_run": False}
    )
    assert r.status_code == 200, r.text[:300]
    job_id = r.json().get("job_id")
    assert job_id, r.json()

    paused = _poll(client, job_id, {"awaiting_approval", "done", "error"})
    assert paused["state"] == "awaiting_approval"
    assert paused["pending_node"] == "gate"
    assert "act" not in paused["node_outputs"]  # downstream gated

    # approve via the real endpoint
    rr = client.post(f"/v1/workflows/jobs/{job_id}/resume", json={"approved": True})
    assert rr.status_code == 200, rr.text[:300]
    assert rr.json()["approved"] is True

    done = _poll(client, job_id, {"done", "error"})
    assert done["state"] == "done"
    assert done["node_outputs"]["act"]["text"] == "shipped: ship it"


def test_resume_when_not_paused_is_409(client: TestClient):
    _login(client)
    wf = {
        "nodes": [{"id": "o", "kind": "output", "config": {"output_template": "x"}}],
        "edges": [],
    }
    r = client.post("/v1/workflows/execute", json={"workflow": wf, "dry_run": False})
    job_id = r.json()["job_id"]
    _poll(client, job_id, {"done", "error"})
    rr = client.post(f"/v1/workflows/jobs/{job_id}/resume", json={"approved": True})
    assert rr.status_code == 409
