"""Auth/session round — /oauth/authorize must PROVE the subject, not accept it.

Handoff §6 LANDMINE: the MVP authorize endpoint read subject/tenant/roles
straight from the query string (`user_subject`) or `x-abs-user-sub` header with
no auth dependency. Not exploitable today (no OAuthClient is seeded in a default
deploy), but the endpoint is mounted and its RS256 tokens are consumed by
deps.get_auth_context — so the moment a client is registered it would be a full
auth-bypass / privilege-escalation. Fix: in production the subject comes only
from an authenticated panel session; tenant + roles are derived server-side.

The non-prod demo path (no login UI) is preserved for the existing harness.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone

import bcrypt
import jwt as _jwt
from sqlmodel import Session

from app.auth.oauth.models import OAuthClient
from app.config import settings
from app.db.session import get_engine


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


def _seed_client(client_id: str, redirect: str = "https://app.local/callback") -> None:
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris=redirect,
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()


def _seed_user(
    email: str, role: str, status: str = "active", pw: str = "pw12345!"
) -> str:
    from app.db.models import User

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


def test_prod_rejects_caller_asserted_subject(client, monkeypatch):
    """env=prod + no session: caller-supplied user_subject must NOT mint."""
    monkeypatch.setattr(settings, "env", "prod")
    cid = f"prod-c-{secrets.token_hex(3)}"
    _seed_client(cid)
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "user_subject": "admin",
            "roles": "admin",
            "tenant_id": "victim",
        },
        follow_redirects=False,
    )
    assert r.status_code == 401, r.text


def test_prod_rejects_x_abs_user_sub_header(client, monkeypatch):
    """env=prod: the x-abs-user-sub header is equally untrusted."""
    monkeypatch.setattr(settings, "env", "prod")
    cid = f"prod-h-{secrets.token_hex(3)}"
    _seed_client(cid)
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
        },
        headers={"x-abs-user-sub": "admin"},
        follow_redirects=False,
    )
    assert r.status_code == 401, r.text


def test_prod_session_subject_overrides_spoofed_query(client, monkeypatch):
    """env=prod + authenticated session: the minted token's subject + roles
    come from the session/user record, NOT the spoofed query params."""
    monkeypatch.setattr(settings, "env", "prod")
    email = "realadmin@demo.local"
    _seed_user(email, "admin")
    cid = f"prod-s-{secrets.token_hex(3)}"
    _seed_client(cid)

    # NB: under env=prod the login cookie is Secure, which the http TestClient
    # won't echo — set the (otherwise identical) session token directly so the
    # authenticated path is exercised. In real prod the cookie rides HTTPS.
    from app.api.auth import COOKIE_NAME, _create_token

    client.cookies.set(COOKIE_NAME, _create_token(email, tenant="default"))

    verifier = "v" * 64
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://app.local/callback",
            "scope": "openid profile",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            # Attacker-style spoof attempt — must be ignored.
            "user_subject": "attacker",
            "roles": "superadmin",
            "tenant_id": "victim-tenant",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    code = r.headers["location"].split("code=", 1)[1].split("&", 1)[0]

    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": cid,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    claims = _jwt.decode(
        tok.json()["access_token"],
        options={"verify_signature": False},
    )
    assert claims["sub"] == email, "subject must be the session user, not 'attacker'"
    assert claims.get("roles") == ["admin"], "roles from users table, not query"
    assert "victim-tenant" not in str(claims.get("tnt") or "")


def test_nonprod_demo_subject_path_preserved(client, monkeypatch):
    """env=dev (test harness): the explicit user_subject path still works so
    the login-UI-less demo + the existing OAuth tests keep passing."""
    monkeypatch.setattr(settings, "env", "dev")
    cid = f"dev-c-{secrets.token_hex(3)}"
    _seed_client(cid)
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "user_subject": "demo-user",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
