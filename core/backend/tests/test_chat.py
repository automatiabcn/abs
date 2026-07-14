"""Phase A — `/v1/chat/*` smoke + golden path tests.

Auth: pre-login via `/auth/login` so the panel session cookie is attached
to TestClient. Cascade: ABS_ANTHROPIC_MOCK_MODE=happy supplied via
`_chat_mock_env` so the cascade router answers deterministically.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _chat_mock_env(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "ok", raising=False)
    yield


@pytest.fixture(autouse=True)
def _wipe_default_tenant_chat_state():
    """earlier tests (q10/q11/q12 cascade + setup sweeps)
    leave ChatSession + ChatMessage rows on `tenant_slug="default"`,
    the bootstrap admin's tenant resolved by chat.py for `admin@local`.
    `test_chat_sessions_empty_list` asserts the GET returns `[]`; any
    leftover session breaks it. Per-test wipe makes the contract
    suite-order independent."""
    from sqlmodel import Session, select

    from app.db.models import ChatMessage, ChatSession
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        leftover = db.exec(
            select(ChatSession).where(ChatSession.tenant_slug == "default")
        ).all()
        for sess in leftover:
            for msg in db.exec(
                select(ChatMessage).where(ChatMessage.session_id == sess.id)
            ).all():
                db.delete(msg)
            db.delete(sess)
        db.commit()
    yield


@pytest.fixture()
def auth_client(client):
    """Login as the bootstrap admin and return the cookie-laden client."""
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


# ───── Sessions CRUD ─────────────────────────────────────────────────────


def test_chat_sessions_empty_list(auth_client):
    r = auth_client.get("/v1/chat/sessions")
    assert r.status_code == 200
    assert r.json() == []


def test_chat_create_session(auth_client):
    r = auth_client.post("/v1/chat/sessions", json={"title": "Test sohbeti"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["title"] == "Test sohbeti"
    assert data["message_count"] == 0
    assert data["tenant_slug"] == "default"


def test_chat_create_session_default_title(auth_client):
    r = auth_client.post("/v1/chat/sessions", json={})
    assert r.status_code == 201
    assert r.json()["title"] == "New chat"


def test_chat_rename_session(auth_client):
    sid = auth_client.post("/v1/chat/sessions", json={"title": "Old"}).json()["id"]
    r = auth_client.patch(f"/v1/chat/sessions/{sid}", json={"title": "New title"})
    assert r.status_code == 200
    assert r.json()["title"] == "New title"


def test_chat_delete_session(auth_client):
    sid = auth_client.post("/v1/chat/sessions", json={}).json()["id"]
    r = auth_client.delete(f"/v1/chat/sessions/{sid}")
    assert r.status_code == 204
    # Subsequent GET messages 404
    r2 = auth_client.get(f"/v1/chat/sessions/{sid}/messages")
    assert r2.status_code == 404


def test_chat_session_404_for_missing(auth_client):
    r = auth_client.get("/v1/chat/sessions/9999/messages")
    assert r.status_code == 404


# ───── Auth gate ─────────────────────────────────────────────────────────


def test_chat_completions_requires_auth(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "merhaba"}]},
    )
    assert r.status_code == 401


def test_chat_sessions_requires_auth(client):
    r = client.get("/v1/chat/sessions")
    assert r.status_code == 401


# ───── Streaming completion ──────────────────────────────────────────────


def _parse_sse(body: bytes) -> list[dict]:
    events: list[dict] = []
    for line in body.decode("utf-8").splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            events.append({"type": "_done"})
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return events


def test_chat_completion_streams_session_text_meta(auth_client):
    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Selam, mock yanıt ver"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    events = _parse_sse(r.content)
    assert any(e.get("type") == "session" for e in events)
    text_events = [e for e in events if e.get("type") == "text"]
    assert text_events, "expected at least one text chunk"
    assert any(e.get("type") == "meta" for e in events)
    assert any(e.get("type") == "_done" for e in events)
    sess_id = next(e for e in events if e.get("type") == "session")["session_id"]

    # Persisted: GET messages should return user + assistant rows.
    msgs = auth_client.get(f"/v1/chat/sessions/{sess_id}/messages").json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


def test_chat_completion_slash_rag_emits_tool_events(auth_client):
    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "/rag müşteri sorusu"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    events = _parse_sse(r.content)
    tool_calls = [e for e in events if e.get("type") == "tool-call"]
    tool_results = [e for e in events if e.get("type") == "tool-result"]
    assert tool_calls and tool_calls[0]["name"] == "rag"
    assert tool_results and tool_results[0]["name"] == "rag_query"


def test_chat_completion_continues_existing_session(auth_client):
    sid = auth_client.post("/v1/chat/sessions", json={"title": "Devam"}).json()["id"]
    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "session_id": sid,
            "messages": [{"role": "user", "content": "test 1"}],
        },
    )
    assert r.status_code == 200
    events = _parse_sse(r.content)
    sess_evt = next(e for e in events if e.get("type") == "session")
    assert sess_evt["session_id"] == sid


def test_chat_completion_rejects_non_user_last_msg(auth_client):
    r = auth_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "assistant", "content": "x"}]},
    )
    assert r.status_code == 400
