# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Device-grant sign-in (V3.2) — the ABS editor's single-identity path.

Contract mirror of abs-editor/extensions/abs-account: start → {device_code,
user_code, verification_uri, interval, expires_in}; poll is always HTTP 200
with either an ``error`` (authorization_pending / slow_down / expired_token /
invalid_grant) or the redeemed token payload.
"""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "CHANGEME"}
    )
    assert r.status_code == 200, r.text
    return client


def _start(client) -> dict:
    r = client.post("/auth/device/start", json={"scopes": ["profile"]})
    assert r.status_code == 200, r.text
    return r.json()


def _age_last_poll(device_code: str) -> None:
    """Rewind last_poll_at so the next poll is outside the slow_down window."""
    import hashlib

    from sqlmodel import Session, select

    from app.auth.device_models import DeviceGrant
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        grant = db.exec(
            select(DeviceGrant).where(
                DeviceGrant.device_code_hash
                == hashlib.sha256(device_code.encode()).hexdigest()
            )
        ).first()
        assert grant is not None
        if grant.last_poll_at is not None:
            grant.last_poll_at = grant.last_poll_at - timedelta(seconds=30)
            db.add(grant)
            db.commit()


def test_start_returns_editor_contract_shape(client):
    data = _start(client)
    assert data["device_code"]
    assert len(data["user_code"]) == 9 and data["user_code"][4] == "-"
    assert "/auth/device?user_code=" in data["verification_uri"]
    assert data["interval"] >= 1
    assert data["expires_in"] > 0


def test_poll_pending_then_slow_down(client):
    data = _start(client)
    r1 = client.post("/auth/device/poll", json={"device_code": data["device_code"]})
    assert r1.status_code == 200
    assert r1.json()["error"] == "authorization_pending"
    # immediate re-poll violates the interval → slow_down
    r2 = client.post("/auth/device/poll", json={"device_code": data["device_code"]})
    assert r2.json()["error"] == "slow_down"


def test_approve_requires_panel_session(client):
    data = _start(client)
    r = client.post("/auth/device/approve", json={"user_code": data["user_code"]})
    assert r.status_code == 401
    assert r.json()["error"] == "login_required"


def test_full_grant_roundtrip_issues_verifiable_editor_token(admin_client):
    """approve (cookie) → poll → abs_mcp_ token that verify_token accepts."""
    from app.api.mcp_tokens import verify_token

    data = _start(admin_client)
    ok = admin_client.post(
        "/auth/device/approve", json={"user_code": data["user_code"]}
    )
    assert ok.status_code == 200, ok.text

    _age_last_poll(data["device_code"])
    r = admin_client.post(
        "/auth/device/poll", json={"device_code": data["device_code"]}
    )
    body = r.json()
    assert "error" not in body, body
    assert body["access_token"].startswith("abs_mcp_")
    assert body["token_type"] == "Bearer"
    assert body["account"]["id"] == "admin@local"

    payload = verify_token(body["access_token"])
    assert payload["scope"] == "all"
    assert payload["actor"] == "admin@local"

    # single-use: the same device_code cannot be redeemed twice
    _age_last_poll(data["device_code"])
    r2 = admin_client.post(
        "/auth/device/poll", json={"device_code": data["device_code"]}
    )
    assert r2.json()["error"] == "invalid_grant"


def test_expired_grant_reports_expired_token(client):
    import hashlib

    from sqlmodel import Session, select

    from app.auth.device_models import DeviceGrant
    from app.db.session import get_engine

    data = _start(client)
    with Session(get_engine()) as db:
        grant = db.exec(
            select(DeviceGrant).where(
                DeviceGrant.device_code_hash
                == hashlib.sha256(data["device_code"].encode()).hexdigest()
            )
        ).first()
        grant.expires_at = grant.issued_at - timedelta(seconds=1)
        db.add(grant)
        db.commit()

    r = client.post("/auth/device/poll", json={"device_code": data["device_code"]})
    assert r.json()["error"] == "expired_token"


def test_unknown_device_code_is_invalid_grant(client):
    r = client.post("/auth/device/poll", json={"device_code": "x" * 43})
    assert r.status_code == 200
    assert r.json()["error"] == "invalid_grant"


def test_approve_unknown_code_404(admin_client):
    r = admin_client.post("/auth/device/approve", json={"user_code": "ZZZZ-ZZZZ"})
    assert r.status_code == 404


def test_approval_page_renders_and_escapes(client):
    ok = client.get("/auth/device", params={"user_code": "BCDF-GHJK"})
    assert ok.status_code == 200
    assert "Approve editor sign-in" in ok.text
    assert 'value="BCDF-GHJK"' in ok.text
    # anything outside the user-code alphabet is dropped, not reflected
    evil = client.get("/auth/device", params={"user_code": '"><script>alert(1)'})
    assert evil.status_code == 200
    assert "<script>alert" not in evil.text
    assert 'value=""' in evil.text


# --- one address cannot lock everyone out (audit 2026-08-18) ----------------

def test_one_address_is_capped_and_others_still_start(client, monkeypatch):
    from app.auth import device as dev

    monkeypatch.setattr(dev, "_STARTS_BY_IP", {})
    for _ in range(dev.MAX_PENDING_PER_IP):
        assert client.post("/auth/device/start", json={"scopes": ["profile"]}).status_code == 200
    r = client.post("/auth/device/start", json={"scopes": ["profile"]})
    assert r.status_code == 429 and r.json()["error"] == "slow_down"
    # a different address is not affected by the first one's spray
    r2 = client.post(
        "/auth/device/start", json={"scopes": ["profile"]},
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    assert r2.status_code == 200


def test_the_global_cap_evicts_the_oldest_instead_of_refusing_everyone(client, monkeypatch):
    from app.auth import device as dev

    monkeypatch.setattr(dev, "_STARTS_BY_IP", {})
    monkeypatch.setattr(dev, "MAX_PENDING_GRANTS", 3)
    monkeypatch.setattr(dev, "MAX_PENDING_PER_IP", 100)
    codes = [client.post("/auth/device/start", json={"scopes": []}).json()["device_code"] for _ in range(3)]
    # the fourth start still succeeds — the oldest pending grant made room
    r = client.post("/auth/device/start", json={"scopes": []})
    assert r.status_code == 200
    # …and the oldest is gone: polling it is invalid_grant, the newest still pends
    assert client.post("/auth/device/poll", json={"device_code": codes[0]}).json()["error"] == "invalid_grant"
    assert client.post("/auth/device/poll", json={"device_code": r.json()["device_code"]}).json()["error"] == "authorization_pending"
