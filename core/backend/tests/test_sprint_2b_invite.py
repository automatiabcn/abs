# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2B BUG-36 — /v1/admin/users/invite flow guard tests."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def test_invite_requires_admin(client):
    r = client.post("/v1/admin/users/invite", json={"email": "x@y.com"})
    assert r.status_code == 401


def test_invite_success_returns_invite_id_without_token(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/users/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "operator@demo-acme.com", "role": "member"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "operator@demo-acme.com"
    assert body["role"] == "member"
    assert body["status"] == "pending"
    # Magic-link plaintext + hash MUST NOT leak via the wire.
    assert "magic_token" not in body
    assert "magic_token_hash" not in r.text


def test_duplicate_pending_invite_returns_409(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/v1/admin/users/invite",
        headers=headers,
        json={"email": "dup@demo-acme.com", "role": "member"},
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/admin/users/invite",
        headers=headers,
        json={"email": "dup@demo-acme.com", "role": "member"},
    )
    assert second.status_code == 409
    body = second.json()
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("error") == "duplicate_pending_invite"
        assert detail.get("invite_id") == first.json()["invite_id"]


def test_list_invites_includes_pending_row(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    posted = client.post(
        "/v1/admin/users/invite",
        headers=headers,
        json={"email": "list-row@demo-acme.com", "role": "member"},
    )
    assert posted.status_code == 201
    r = client.get("/v1/admin/users/invites", headers=headers)
    assert r.status_code == 200
    emails = [inv["email"] for inv in r.json()["invites"]]
    assert "list-row@demo-acme.com" in emails


def test_revoke_invite_flips_status_to_revoked(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    posted = client.post(
        "/v1/admin/users/invite",
        headers=headers,
        json={"email": "revoke@demo-acme.com", "role": "member"},
    )
    invite_id = posted.json()["invite_id"]
    r = client.delete(
        f"/v1/admin/users/invite/{invite_id}", headers=headers
    )
    assert r.status_code == 204

    # Revoking again should now fail with 409 (status_revoked).
    r2 = client.delete(
        f"/v1/admin/users/invite/{invite_id}", headers=headers
    )
    assert r2.status_code == 409


def test_magic_link_helper_hashes_via_hmac(monkeypatch):
    from app.auth.magic_link import (
        create_magic_link_token,
        hash_magic_token,
        verify_magic_token,
    )

    plaintext, digest, expires_at = create_magic_link_token(
        "x@y.com", "tnt-demo", ttl_minutes=60, purpose="invite"
    )
    assert plaintext != digest
    assert digest == hash_magic_token(plaintext)
    assert verify_magic_token(
        plaintext,
        digest,
        expires_at,
        purpose="invite",
        expected_purpose="invite",
    )
    assert not verify_magic_token(
        plaintext,
        digest,
        expires_at,
        purpose="login",
        expected_purpose="invite",
    )
