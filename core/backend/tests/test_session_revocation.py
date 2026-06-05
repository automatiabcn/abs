"""Auth/session round — server-side session invalidation.

A valid, unexpired ``abs_session`` cookie must stop working the moment the
underlying ``users`` row is deactivated. Before this, logout was purely
client-side: a revoked or demoted admin kept full panel + token-mint access
for the remaining 7-day cookie lifetime. The bootstrap admin (no users row,
admin_credentials.json overlay) must NOT be affected — otherwise the
single-admin self-host operator could lock themselves out.
"""

from __future__ import annotations

import bcrypt


def _seed(email: str, role: str, status: str, pw: str = "pw12345!") -> str:
    from sqlmodel import Session

    from app.db.models import User
    from app.db.session import get_engine

    h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    with Session(get_engine()) as s:
        s.add(
            User(
                email=email,
                password_hash=h,
                tenant_slug="default",
                role=role,
                status=status,
            )
        )
        s.commit()
    return pw


def _set_status(email: str, status: str) -> None:
    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    with Session(get_engine()) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        assert u is not None
        u.status = status
        s.add(u)
        s.commit()


def test_revoked_admin_loses_session_and_mint(client):
    """Active admin can mint MCP tokens; once suspended, both /auth/me and the
    mint endpoint reject the still-valid cookie."""
    email = "revokeme@demo.local"
    pw = _seed(email, "admin", "active")

    login = client.post("/auth/login", json={"email": email, "password": pw})
    assert login.status_code == 200, login.text

    # Active: session probe + token mint both succeed.
    assert client.get("/auth/me").status_code == 200
    mint = client.post(
        "/v1/mcp/tokens", json={"label": "ci-token", "scope": "all", "ttl_days": 30}
    )
    assert mint.status_code == 201, mint.text

    # Revoke the user in the DB — cookie is untouched and still cryptographically
    # valid, so this only takes effect if the server rechecks active status.
    _set_status(email, "suspended")

    assert client.get("/auth/me").status_code == 401, "revoked session must 401"
    mint2 = client.post(
        "/v1/mcp/tokens", json={"label": "after-revoke", "scope": "all", "ttl_days": 30}
    )
    assert mint2.status_code == 401, "revoked admin must not mint tokens"


def test_pending_user_session_rejected(client):
    """A 'pending' (unclaimed) row must not authenticate a session even if a
    cookie was somehow minted for it."""
    email = "pendinguser@demo.local"
    _seed(email, "admin", "pending")
    from app.api.auth import COOKIE_NAME, _create_token

    client.cookies.set(COOKIE_NAME, _create_token(email, tenant="default"))
    assert client.get("/auth/me").status_code == 401


def test_bootstrap_subject_without_users_row_still_valid(client):
    """No users row (bootstrap admin / legacy deploy) is NOT treated as
    revoked — the operator keeps their panel. Proves the recheck is fail-safe.
    """
    from app.api.auth import COOKIE_NAME, _create_token

    client.cookies.set(
        COOKIE_NAME, _create_token("ghost-bootstrap@nowhere.local", tenant="default")
    )
    r = client.get("/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "ghost-bootstrap@nowhere.local"
