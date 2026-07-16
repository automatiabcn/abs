# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The signed-in operator can reach their own /v1/me/* self-service surfaces.

On a self-host box the account holder logs into the operator panel with a
session cookie, not the raw Bearer license token. Before the panel-session
fallback (app/api/me_auth.py) the GDPR self-service endpoints answered 401 to
that cookie, so the Account/Privacy page had no way to call them. These tests
pin the fallback: a valid panel session resolves the server's own license
identity, and *without* either a Bearer token or a session the endpoints still
deny — the fallback widens the door, it doesn't remove the lock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from sqlmodel import Session, select

from app.config import settings
from app.db.models import License
from app.db.session import get_engine
from app.licensing import generate_license


def _seed_server_license(monkeypatch, email: str = "operator@local") -> str:
    """Give the server a real, verifiable license (as a self-host box has) and
    a matching License row, and point settings.license_key at it."""
    token = generate_license("cust_selfhost", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if not db.scalars(select(License).where(License.jti == jti)).first():
            db.add(
                License(
                    jti=jti,
                    customer_email=email,
                    customer_id_stripe="cus_selfhost",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
            db.commit()
    monkeypatch.setattr(settings, "license_key", token, raising=False)
    return jti


def _login_panel(client) -> None:
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


# ---- fallback resolves the account for a signed-in operator ------------


def test_audit_log_reachable_with_panel_session(client, monkeypatch) -> None:
    _seed_server_license(monkeypatch)
    _login_panel(client)
    # No Authorization header — the panel cookie must stand in.
    r = client.get("/v1/me/audit-log")
    assert r.status_code == 200, r.text
    assert "entries" in r.json()


def test_consents_reachable_with_panel_session(client, monkeypatch) -> None:
    _seed_server_license(monkeypatch)
    _login_panel(client)
    r = client.get("/v1/me/consents")
    assert r.status_code == 200, r.text


def test_deletion_status_reachable_with_panel_session(client, monkeypatch) -> None:
    _seed_server_license(monkeypatch)
    _login_panel(client)
    r = client.get("/v1/me/account/deletion-status")
    assert r.status_code == 200, r.text


def test_data_export_reachable_with_panel_session(client, monkeypatch) -> None:
    _seed_server_license(monkeypatch)
    _login_panel(client)
    r = client.post("/v1/me/data-export")
    assert r.status_code == 200, r.text
    # The export is attributed to the server license, not an anonymous caller.
    body = r.json()
    assert body.get("job_id")


# ---- the lock is still there ------------------------------------------


def test_me_endpoints_still_401_without_session_or_bearer(client) -> None:
    for path in ("/v1/me/audit-log", "/v1/me/consents", "/v1/me/account/deletion-status"):
        r = client.get(path)
        assert r.status_code == 401, f"{path} → {r.status_code}"


def test_keyless_trial_resolves_to_operator_identity(client, monkeypatch) -> None:
    # Keyless (trial) self-host: no license row yet, so the operator's own
    # identity is the account — the same key trial-mode audit/consent rows
    # already use. The endpoint resolves rather than locking the operator out.
    monkeypatch.setattr(settings, "license_key", "", raising=False)
    _login_panel(client)
    r = client.get("/v1/me/audit-log")
    assert r.status_code == 200, r.text
    assert "entries" in r.json()
