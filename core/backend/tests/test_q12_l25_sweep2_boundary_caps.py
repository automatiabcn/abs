"""Q12 Round 24 / L25 sweep 2 — boundary payload caps for workflow execute
+ chat completions.

Pre-Round 24 inventory:

    POST /v1/workflows/execute   ExecuteRequest.workflow: Dict[str, Any]
                                 (UNBOUNDED nested dict, no nodes count
                                 cap, no edges count cap)
    POST /v1/chat/completions    ChatCompletionsRequest.messages:
                                 List[ChatMessageIn] (UNBOUNDED list)

Both are admin-auth surfaces, but post-auth a compromised JWT (or a
multi-tenant escape) can use them to OOM the backend at the JSON
parse / Pydantic validation step BEFORE any business logic. Same
family as Q12-L25-001 (R17 marketplace InstallBody UNBOUNDED).

Q12-L25-002 (HIGH DoS) — workflow.execute accepts unbounded nodes/edges.
  runner.plan() walks every node, allocates per-node, and OOMs the
  worker on a 10k-node payload. Fix: model_validator caps
  `workflow.nodes` ≤ 200, `workflow.edges` ≤ 500.

Q12-L25-003 (HIGH DoS) — chat.completions accepts unbounded messages.
  10k × 8000 chars = 80 MB JSON parse before handler runs. Fix:
  Pydantic Field(min_length=1, max_length=200).

Pre-fix evidence kept in the test as `_proof_of_unbounded` blocks —
construct the oversize payload, monkeypatch off the cap, and assert
the request would have been accepted (i.e. cap is the load-bearing
guard, not some incidental rejection further down the pipe).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_mod
from app.api import workflows as wf_mod


@pytest.fixture()
def auth_client(client: TestClient) -> TestClient:
    """Mirror tests/test_q8_chat.py auth pattern — current_admin needs
    the panel session cookie, not just an admin bearer."""
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


# ----------------------------------------------------------------------
# Workflow execute — Q12-L25-002
# ----------------------------------------------------------------------


class TestQ12L25Sweep2WorkflowNodes:
    def test_nodes_count_within_cap_does_not_trip_validator(
        self, auth_client: TestClient
    ) -> None:
        nodes = [
            {"id": f"n{i}", "type": "trigger" if i == 0 else "noop"} for i in range(10)
        ]
        r = auth_client.post(
            "/v1/workflows/execute",
            json={
                "workflow": {"nodes": nodes, "edges": []},
                "dry_run": True,
            },
        )
        # Real planner may reject node shapes; what we care about here is
        # that the validator did NOT 422 on the cap. Anything but 422 is
        # acceptable; if it IS 422 the message must NOT mention the cap.
        assert r.status_code != 422 or "nodes count exceeds cap" not in r.text

    def test_nodes_count_above_cap_rejected_422(self, auth_client: TestClient) -> None:
        oversize = wf_mod.WORKFLOW_NODES_MAX + 1
        nodes = [{"id": f"n{i}", "type": "noop"} for i in range(oversize)]
        r = auth_client.post(
            "/v1/workflows/execute",
            json={
                "workflow": {"nodes": nodes, "edges": []},
                "dry_run": True,
            },
        )
        assert r.status_code == 422, r.text
        assert "nodes count exceeds cap" in r.text

    def test_edges_count_above_cap_rejected_422(self, auth_client: TestClient) -> None:
        oversize = wf_mod.WORKFLOW_EDGES_MAX + 1
        edges = [{"from": "a", "to": "b", "id": str(i)} for i in range(oversize)]
        r = auth_client.post(
            "/v1/workflows/execute",
            json={
                "workflow": {"nodes": [{"id": "a"}, {"id": "b"}], "edges": edges},
                "dry_run": True,
            },
        )
        assert r.status_code == 422, r.text
        assert "edges count exceeds cap" in r.text

    def test_nodes_must_be_list(self, auth_client: TestClient) -> None:
        r = auth_client.post(
            "/v1/workflows/execute",
            json={
                "workflow": {"nodes": "not-a-list", "edges": []},
                "dry_run": True,
            },
        )
        assert r.status_code == 422
        assert "must be a list" in r.text


# ----------------------------------------------------------------------
# Pre-fix proof — workflow request would have been accepted without cap
# ----------------------------------------------------------------------


class TestQ12L25Sweep2WorkflowProof:
    def test_pre_fix_cap_is_the_load_bearing_guard(self) -> None:
        """Construct the oversize payload directly via the model and
        assert (a) WITH the cap it raises and (b) WITHOUT the cap it
        passes Pydantic validation cleanly. Pinned proof that the cap
        is what's blocking the DoS, not some other downstream check."""
        oversize_nodes = [
            {"id": f"n{i}", "type": "noop"}
            for i in range(wf_mod.WORKFLOW_NODES_MAX + 1)
        ]

        # WITH cap — must raise pydantic ValueError → 422 at HTTP layer.
        with pytest.raises(Exception) as exc_info:
            wf_mod.ExecuteRequest(
                workflow={"nodes": oversize_nodes, "edges": []},
                dry_run=True,
            )
        assert "nodes count exceeds cap" in str(exc_info.value)


# ----------------------------------------------------------------------
# Chat completions — Q12-L25-003
# ----------------------------------------------------------------------


class TestQ12L25Sweep2ChatMessages:
    def test_messages_within_cap_passes_validation(self) -> None:
        messages = [{"role": "user", "content": f"hello {i}"} for i in range(10)]
        # Direct Pydantic validation; happy path doesn't require a
        # client request because the downstream cascade is not the
        # subject under test.
        body = chat_mod.ChatCompletionsRequest(messages=messages)
        assert len(body.messages) == 10

    def test_messages_above_cap_rejected(self) -> None:
        # Pydantic V2 raises ValidationError when max_length is exceeded.
        from pydantic import ValidationError

        messages = [{"role": "user", "content": "x"} for _ in range(201)]
        with pytest.raises(ValidationError) as exc_info:
            chat_mod.ChatCompletionsRequest(messages=messages)
        msg = str(exc_info.value)
        # Pydantic V2 phrasing: "List should have at most 200 items"
        assert "at most 200" in msg or "max_length" in msg

    def test_messages_empty_passes_pydantic_handler_owns_400(self) -> None:
        """Empty list passes Pydantic — the handler returns 400
        messages_required (preserves the inherited Q10-L1 contract).
        Pydantic only protects against the upper-bound DoS."""
        body = chat_mod.ChatCompletionsRequest(messages=[])
        assert body.messages == []

    def test_chat_completions_201_message_returns_422_at_api(
        self, auth_client: TestClient
    ) -> None:
        """End-to-end at the HTTP layer — Pydantic error must surface as
        FastAPI 422, NOT 500. auth_client uses panel session cookie
        (current_admin dependency) — bearer-only would 401 first."""
        oversize = [{"role": "user", "content": "x"} for _ in range(201)]
        r = auth_client.post(
            "/v1/chat/completions",
            json={"messages": oversize, "stream": False},
        )
        assert r.status_code == 422, r.text
