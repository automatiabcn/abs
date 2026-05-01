"""Q10 Round 6 / L2 — integration roundtrip tests.

Three contracts that previously had only happy-path unit coverage:

  1. Cascade run + chat completions: prompt arrives, mock provider
     answers, SSE chunks land, assistant message persists, sidebar
     session list reflects the new message_count.

  2. Tool browser inventory: GET /v1/panel/tools returns the contract
     (total + category_counts + tools[]) the panel/tools page expects.

  3. Cascade providers status: GET /v1/cascade/providers structure
     used by /admin/providers cards (active + missing + total +
     anthropic_mock_mode).
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "ok", raising=False)
    yield


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


# ───── 1. Cascade + chat roundtrip ──────────────────────────────────────


class TestCascadeChatRoundtrip:
    def test_completions_persists_user_and_assistant_messages(
        self, admin_client
    ):
        # Fire a streaming completion, parse SSE, then verify the session
        # holds both rows.
        resp = admin_client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "Q10 L2 integration ping"}
                ],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        events = []
        for line in resp.content.decode("utf-8").splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue

        sess = next(e for e in events if e.get("type") == "session")
        sid = sess["session_id"]

        # text + meta event present
        assert any(e.get("type") == "text" for e in events)
        assert any(e.get("type") == "meta" for e in events)

        # GET messages list reflects user + assistant
        msgs = admin_client.get(f"/v1/chat/sessions/{sid}/messages").json()
        roles = [m["role"] for m in msgs]
        assert "user" in roles and "assistant" in roles

        # Session list includes our session with message_count >= 2
        sessions = admin_client.get("/v1/chat/sessions").json()
        ours = [s for s in sessions if s["id"] == sid]
        assert len(ours) == 1
        assert ours[0]["message_count"] >= 2

        # Cleanup so the suite stays idempotent under repeat runs.
        admin_client.delete(f"/v1/chat/sessions/{sid}")

    def test_cascade_run_direct_returns_mock_provider(self, admin_client):
        r = admin_client.post(
            "/v1/cascade/run",
            json={"prompt": "Q10 L2 cascade ping", "max_tokens": 32},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mock"] is True
        assert body["provider"] == "anthropic-mock"
        assert isinstance(body["fallback_chain"], list)
        assert "anthropic-mock" in body["fallback_chain"]


# ───── 2. Panel tool inventory contract ─────────────────────────────────


class TestPanelToolsContract:
    def test_panel_tools_returns_inventory_shape(self, admin_client):
        r = admin_client.get("/v1/panel/tools")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body and isinstance(body["total"], int)
        assert "category_counts" in body
        assert isinstance(body["category_counts"], dict)
        assert "tools" in body and isinstance(body["tools"], list)

    def test_panel_tools_each_row_has_contract_fields(self, admin_client):
        body = admin_client.get("/v1/panel/tools").json()
        for tool in body["tools"][:10]:
            assert isinstance(tool["name"], str) and tool["name"]
            assert "category" in tool
            assert isinstance(tool.get("description", ""), str)
            schema = tool.get("input_schema") or {}
            assert "required" in schema
            assert "properties" in schema
            assert isinstance(schema["properties"], list)


# ───── 3. Cascade providers status contract ─────────────────────────────


class TestCascadeProvidersStatus:
    def test_providers_endpoint_shape(self, admin_client):
        r = admin_client.get("/v1/cascade/providers")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "active",
            "missing",
            "configured_count",
            "total",
            "anthropic_mock_mode",
        ):
            assert key in body, f"missing key: {key}"
        assert isinstance(body["active"], list)
        assert isinstance(body["missing"], list)
        assert body["configured_count"] + len(body["missing"]) >= body["total"] - 1

    def test_providers_mock_mode_reflected(self, admin_client):
        body = admin_client.get("/v1/cascade/providers").json()
        # autouse fixture sets it to 'ok'
        assert body["anthropic_mock_mode"] == "ok"


# ───── 4. Chat session lifecycle (create → rename → delete) ─────────────


class TestChatSessionLifecycle:
    def test_session_create_rename_delete_cycle(self, admin_client):
        sid = admin_client.post(
            "/v1/chat/sessions", json={"title": "q10-l2-cycle"}
        ).json()["id"]
        rename = admin_client.patch(
            f"/v1/chat/sessions/{sid}", json={"title": "renamed"}
        )
        assert rename.status_code == 200
        assert rename.json()["title"] == "renamed"

        d = admin_client.delete(f"/v1/chat/sessions/{sid}")
        assert d.status_code == 204
        again = admin_client.get(f"/v1/chat/sessions/{sid}/messages")
        assert again.status_code == 404
