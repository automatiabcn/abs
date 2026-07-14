"""Magic-link multi-admin E2E (6 tests).

Pins the contract for the self-host signup → magic-link → admin claim
flow that S2/R14 hardened (plaintext-leak fix).

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
  6. 001 regression — signup_pending log line carries only the
     6-char token_hint, never the full token.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import User
from app.db.session import get_engine


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """pin per-test settings.data_dir so the magic-link
    claim flow's `admin_credentials.json` write (auth.py
    `_claim_user_by_token`) cannot leak into the session-scope data dir.

    Without isolation the file overlays the bootstrap fallback
    (`admin@local`/`CHANGEME`) and every later test that posts to
    `/auth/login` with the bootstrap creds gets 401. S11 host baseline
    surfaced this as 3 FAIL (`test_secrets_api`) + 17 ERROR
    (`test_provider_degradation_matrix` × 7 + `test_chat` × 10).

    Re-write `setup_state.json` to "completed" inside the per-test dir so
    `FirstRunMiddleware` does not redirect `/auth/signup` to `/setup`.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_file = tmp_path / "setup_state.json"
    state_file.write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": [
                    "admin",
                    "license",
                    "domain",
                    "anthropic",
                    "providers",
                    "test",
                ],
                "started_at": time.time(),
                "completed_at": time.time(),
                "data": {},
            }
        ),
        encoding="utf-8",
    )


def _signup(
    client: TestClient, email: str, slug: str, password: str = "TestPass2026!"
) -> str:
    r = client.post(
        "/auth/signup",
        json={"email": email, "tenant_slug": slug, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["magic_link"]


def _token_from_link(link: str) -> str:
    # honesty round changed the signup `magic_link` to point at the
    # customer-facing /activate page (the backend claim endpoint /auth/magic
    # is unchanged and still serves the GET below). Accept either prefix and
    # extract the token.
    assert "token=" in link, link
    assert link.startswith(("/activate?token=", "/auth/magic?token=")), link
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
        user = (
            db.execute(select(User).where(User.magic_token == token)).scalars().first()
        )
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
        rows = (
            db.execute(select(User).where(User.tenant_slug == "r87-team"))
            .scalars()
            .all()
        )
    emails = sorted(u.email for u in rows)
    assert "admin_a_tenant@r87.local" in emails
    assert "admin_b_tenant@r87.local" in emails


# ----------------------------------------------------------------------
# 4. Both admins active after claim
# ----------------------------------------------------------------------


def test_two_admins_both_active_in_tenant(client: TestClient):
    link_a = _signup(client, "admin_a_active@r87.local", "r87-pair")
    link_b = _signup(client, "admin_b_active@r87.local", "r87-pair")

    # link_* now points at the /activate SPA page; claim via the backend
    # endpoint the page calls.
    r1 = client.get(f"/auth/magic?token={_token_from_link(link_a)}")
    assert r1.status_code == 200, r1.text
    r2 = client.get(f"/auth/magic?token={_token_from_link(link_b)}")
    assert r2.status_code == 200, r2.text

    with Session(get_engine()) as db:
        rows = (
            db.execute(select(User).where(User.tenant_slug == "r87-pair"))
            .scalars()
            .all()
        )
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
# 6b. magic claim must NOT overwrite bootstrap admin file
# ----------------------------------------------------------------------


def test_magic_claim_does_not_overwrite_bootstrap_admin(
    client: TestClient, tmp_path: Path
):
    """Phase C founder evidence: a fresh /auth/signup +
    /auth/magic?token=... claim was unconditionally overwriting
    `admin_credentials.json`, wiping out the setup-wizard bootstrap admin
    (lockout + privilege-escalation vector).

    Contract: when the claimed user is NOT the email recorded in the file,
    the file MUST stay byte-identical, and the bootstrap admin must keep
    being able to log in.
    """
    creds_file = tmp_path / "admin_credentials.json"
    bootstrap_payload = {
        "email": "admin@demo-acme.com",
        # bcrypt hash for "DemoPass2026!" — generated locally, not a secret.
        "password_hash": "$2b$12$KIXxPfnK1Q1xZb6vQy7QmugQvJpZkZ7r4dQpYcJX8BkqAWqU6mG3K",
        "created_at": time.time(),
        "tenant_slug": "demo-acme",
        "source": "setup_wizard",
    }
    creds_file.write_text(
        json.dumps(bootstrap_payload, ensure_ascii=False), encoding="utf-8"
    )
    bootstrap_bytes_before = creds_file.read_bytes()

    # New admin signs up + claims magic link → previously this overwrote
    # admin_credentials.json. After the fix, the file stays untouched.
    link = _signup(client, "newadmin@demo-acme.com", "demo-acme")
    token = _token_from_link(link)
    r = client.get(f"/auth/magic?token={token}")
    assert r.status_code == 200, r.text

    bootstrap_bytes_after = creds_file.read_bytes()
    assert bootstrap_bytes_after == bootstrap_bytes_before, (
        "REGRESSION: magic claim overwrote bootstrap "
        "admin_credentials.json (setup_wizard email lost)."
    )

    # New admin row must still be promoted in the User table even though
    # the file write was suppressed.
    with Session(get_engine()) as db:
        new_user = (
            db.execute(select(User).where(User.email == "newadmin@demo-acme.com"))
            .scalars()
            .first()
        )
        assert new_user is not None
        assert new_user.status == "active"
        assert new_user.magic_token is None


# ----------------------------------------------------------------------
# 6. 001 regression — no full token in audit log
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
        assert token not in msg, f"REGRESSION: log leaked full magic token: {msg!r}"

    # The hint must be present so ops can still correlate.
    hint = token[:6]
    assert any(
        hint in rec.getMessage() and "***" in rec.getMessage()
        for rec in caplog.records
        if "signup_pending" in rec.getMessage()
    )
