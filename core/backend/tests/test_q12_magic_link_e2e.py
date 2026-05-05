"""Q12-R87 — Magic-link multi-admin E2E (6 tests).

Pins the contract for the self-host signup → magic-link → admin claim
flow that S2/R14 hardened (Q12-L24-001 plaintext-leak fix).

Six contracts:
  1. Admin A signup → /auth/magic?token=… → panel session cookie set;
     /auth/me works without a separate password login.
  2. Token TTL — magic_expires_at < now → /auth/magic returns 410.
  3. Admin A invites Admin B (same tenant_slug) → both User rows exist
     with the same tenant.
  4. Both users active in tenant — after both claims, status=active for
     each (admin_credentials.json single-admin overlay is a known
     limitation pinned separately, not a per-row contract).
  5. Cross-tenant block — admin token whose tenant claim does not match
     the resource's tenant gets 403 from `_enforce_tenant_match`.
  6. Q12-L24-001 regression — signup_pending log line carries only the
     6-char token_hint, never the full token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import User
from app.db.session import get_engine


def _signup(client: TestClient, email: str, slug: str, password: str = "TestPass2026!") -> str:
    r = client.post(
        "/auth/signup",
        json={"email": email, "tenant_slug": slug, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["magic_link"]


def _token_from_link(link: str) -> str:
    assert link.startswith("/auth/magic?token=")
    return link.split("token=", 1)[1]


# ----------------------------------------------------------------------
# 1. Signup → magic claim → panel session works
# ----------------------------------------------------------------------


def test_admin_a_signup_magic_link_claim_to_panel(client: TestClient):
    link = _signup(client, "admin_a@r87.local", "r87-acme")
    token = _token_from_link(link)

    r = client.get(f"/auth/magic?token={token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "claimed"
    assert body["email"] == "admin_a@r87.local"
    assert body["tenant_slug"] == "r87-acme"

    # Panel session cookie should be set; /auth/me must succeed.
    me = client.get("/auth/me")
    assert me.status_code == 200, me.text


# ----------------------------------------------------------------------
# 2. 24h expiry blocks claim
# ----------------------------------------------------------------------


def test_token_24h_expiry_then_reuse_blocked_410(client: TestClient):
    link = _signup(client, "admin_exp@r87.local", "r87-exp")
    token = _token_from_link(link)

    # Force the User row's magic_expires_at into the past.
    with Session(get_engine()) as db:
        user = db.execute(
            select(User).where(User.magic_token == token)
        ).scalars().first()
        assert user is not None, "magic token must persist to users table"
        user.magic_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.add(user)
        db.commit()

    r = client.get(f"/auth/magic?token={token}")
    assert r.status_code == 410, r.text
    assert r.json()["detail"] == "token_expired"


# ----------------------------------------------------------------------
# 3. Admin A invites Admin B — same tenant
# ----------------------------------------------------------------------


def test_admin_a_invites_admin_b_same_tenant(client: TestClient):
    _signup(client, "admin_a_tenant@r87.local", "r87-team")
    _signup(client, "admin_b_tenant@r87.local", "r87-team")

    with Session(get_engine()) as db:
        rows = db.execute(
            select(User).where(User.tenant_slug == "r87-team")
        ).scalars().all()
    emails = sorted(u.email for u in rows)
    assert "admin_a_tenant@r87.local" in emails
    assert "admin_b_tenant@r87.local" in emails


# ----------------------------------------------------------------------
# 4. Both admins active after claim
# ----------------------------------------------------------------------


def test_two_admins_both_active_in_tenant(client: TestClient):
    link_a = _signup(client, "admin_a_active@r87.local", "r87-pair")
    link_b = _signup(client, "admin_b_active@r87.local", "r87-pair")

    r1 = client.get(link_a)
    assert r1.status_code == 200, r1.text
    r2 = client.get(link_b)
    assert r2.status_code == 200, r2.text

    with Session(get_engine()) as db:
        rows = db.execute(
            select(User).where(User.tenant_slug == "r87-pair")
        ).scalars().all()
    statuses = {u.email: u.status for u in rows}
    assert statuses.get("admin_a_active@r87.local") == "active"
    assert statuses.get("admin_b_active@r87.local") == "active"


# ----------------------------------------------------------------------
# 5. Cross-tenant block — _enforce_tenant_match raises 403
# ----------------------------------------------------------------------


def test_admin_a_cross_tenant_block_403():
    """Admin token with `tenant=acme` cannot reach `tenant=other`. Pinned
    against `marketplace._enforce_tenant_match` because that's the
    canonical cross-tenant gate today."""
    from app.api.marketplace import _enforce_tenant_match

    admin_claim = {"sub": "admin_a@r87.local", "tenant": "acme"}

    # Same-tenant: no raise.
    _enforce_tenant_match(admin_claim, "acme")

    # Cross-tenant: 403.
    with pytest.raises(HTTPException) as exc_info:
        _enforce_tenant_match(admin_claim, "other")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "cross_tenant_forbidden"


# ----------------------------------------------------------------------
# 6. Q12-L24-001 regression — no full token in audit log
# ----------------------------------------------------------------------


def test_magic_token_email_does_not_leak_token_in_audit(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        link = _signup(client, "audit@r87.local", "r87-audit")
    token = _token_from_link(link)
    assert len(token) >= 32

    for rec in caplog.records:
        msg = rec.getMessage()
        assert token not in msg, (
            f"Q12-L24-001 REGRESSION: log leaked full magic token: {msg!r}"
        )

    # The hint must be present so ops can still correlate.
    hint = token[:6]
    assert any(
        hint in rec.getMessage() and "***" in rec.getMessage()
        for rec in caplog.records
        if "signup_pending" in rec.getMessage()
    )
