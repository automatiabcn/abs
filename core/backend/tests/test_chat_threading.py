"""Q12 / Brief 3 R4 — chat thread sidebar regression suite.

Covers the four endpoints added in this round:

  * POST /v1/chat/sessions/{id}/pin        (toggle, idempotent re-pin)
  * POST /v1/chat/sessions/{id}/archive    (idempotent re-archive)
  * POST /v1/chat/sessions/{id}/unarchive
  * GET  /v1/chat/sessions?search=&include_archived=  (sidebar list)

Plus the denormalised counters that drive the sort order:
  * last_activity_at bumps on each user / assistant message.
  * message_count increments by 1 per persisted message.

Real LLM calls are clamped via ABS_ANTHROPIC_MOCK_MODE=ok like the
sibling chat suites.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.db.models import ChatMessage, ChatSession
from app.db.session import get_engine


@pytest.fixture(autouse=True)
def _chat_mock_env(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(
        settings, "anthropic_mock_mode", "ok", raising=False
    )
    yield


@pytest.fixture(autouse=True)
def _wipe_default_tenant_chat_state():
    with Session(get_engine()) as db:
        for sess in db.exec(
            select(ChatSession).where(
                ChatSession.tenant_slug == "default"
            )
        ).all():
            for msg in db.exec(
                select(ChatMessage).where(
                    ChatMessage.session_id == sess.id
                )
            ).all():
                db.delete(msg)
            db.delete(sess)
        db.commit()
    yield


@pytest.fixture()
def auth_client(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


def _create(client, title: str) -> dict:
    r = client.post("/v1/chat/sessions", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def test_session_default_threading_metadata(auth_client):
    sess = _create(auth_client, "Sidebar default")
    assert sess["pinned"] is False
    assert sess["archived_at"] is None
    assert sess["last_activity_at"] is not None
    assert sess["message_count"] == 0


def test_pin_toggle_round_trip(auth_client):
    sid = _create(auth_client, "pin-me")["id"]
    on = auth_client.post(f"/v1/chat/sessions/{sid}/pin")
    assert on.status_code == 200
    assert on.json()["pinned"] is True

    off = auth_client.post(f"/v1/chat/sessions/{sid}/pin?pinned=false")
    assert off.status_code == 200
    assert off.json()["pinned"] is False


def test_archive_idempotent_then_unarchive(auth_client):
    sid = _create(auth_client, "archive-me")["id"]

    a1 = auth_client.post(f"/v1/chat/sessions/{sid}/archive").json()
    assert a1["archived_at"] is not None
    first_ts = a1["archived_at"]

    a2 = auth_client.post(f"/v1/chat/sessions/{sid}/archive").json()
    assert a2["archived_at"] == first_ts

    u = auth_client.post(f"/v1/chat/sessions/{sid}/unarchive").json()
    assert u["archived_at"] is None


def test_list_excludes_archived_by_default(auth_client):
    keep_id = _create(auth_client, "keep")["id"]
    arch_id = _create(auth_client, "archived")["id"]
    auth_client.post(f"/v1/chat/sessions/{arch_id}/archive")

    listed = auth_client.get("/v1/chat/sessions").json()
    ids = {s["id"] for s in listed}
    assert keep_id in ids
    assert arch_id not in ids

    with_arch = auth_client.get(
        "/v1/chat/sessions?include_archived=true"
    ).json()
    assert {s["id"] for s in with_arch} >= {keep_id, arch_id}


def test_list_pinned_first_then_recent(auth_client):
    s1 = _create(auth_client, "older")["id"]
    _ = _create(auth_client, "newer")["id"]
    auth_client.post(f"/v1/chat/sessions/{s1}/pin")

    listed = auth_client.get("/v1/chat/sessions").json()
    assert listed[0]["id"] == s1
    assert listed[0]["pinned"] is True


def test_list_search_filters_by_title(auth_client):
    _create(auth_client, "Roadmap discussion")
    _create(auth_client, "Refactor plan")
    _create(auth_client, "Stripe escalation")

    hits = auth_client.get("/v1/chat/sessions?search=stripe").json()
    titles = {s["title"] for s in hits}
    assert "Stripe escalation" in titles
    assert "Roadmap discussion" not in titles


def test_completion_bumps_message_count_and_last_activity(auth_client):
    sid = _create(auth_client, "activity")["id"]
    before = auth_client.get("/v1/chat/sessions").json()
    before_match = next(s for s in before if s["id"] == sid)
    assert before_match["message_count"] == 0
    before_ts = before_match["last_activity_at"]

    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "session_id": sid,
            "messages": [{"role": "user", "content": "merhaba"}],
        },
    )
    assert r.status_code == 200

    after = auth_client.get("/v1/chat/sessions").json()
    after_match = next(s for s in after if s["id"] == sid)
    assert after_match["message_count"] >= 2
    assert after_match["last_activity_at"] >= before_ts


def test_pin_404_for_unknown_session(auth_client):
    r = auth_client.post("/v1/chat/sessions/99999/pin")
    assert r.status_code == 404
