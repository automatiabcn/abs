"""T-003 — OAuth 2.1 HTTP endpoints (FastAPI TestClient end-to-end)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
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


def test_jwks_endpoint_returns_public_key() -> None:
    with TestClient(app) as c:
        r = c.get("/.well-known/jwks.json")
    assert r.status_code == 200
    body = r.json()
    assert body["keys"][0]["alg"] == "RS256"
    assert body["keys"][0]["kty"] == "RSA"
    assert "n" in body["keys"][0] and "e" in body["keys"][0]


def test_openid_configuration_lists_endpoints() -> None:
    with TestClient(app) as c:
        r = c.get("/.well-known/openid-configuration")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["jwks_uri"].endswith("/.well-known/jwks.json")
    assert cfg["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in cfg["grant_types_supported"]
    assert "refresh_token" in cfg["grant_types_supported"]


def test_authorize_requires_user_subject() -> None:
    cid = f"http-c1-{secrets.token_hex(3)}"
    _seed_client(cid)
    with TestClient(app) as c:
        r = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://app.local/callback",
                "code_challenge": _challenge("v" * 64),
                "code_challenge_method": "S256",
            },
        )
    assert r.status_code == 401


def test_full_authorize_token_refresh_via_http() -> None:
    cid = f"http-c2-{secrets.token_hex(3)}"
    _seed_client(cid)
    verifier = "v" * 64
    challenge = _challenge(verifier)

    with TestClient(app) as c:
        r = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://app.local/callback",
                "scope": "openid profile",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
                "user_subject": "user-http",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        location = r.headers["location"]
        assert location.startswith("https://app.local/callback?code=")
        code = location.split("code=", 1)[1].split("&", 1)[0]

        token_resp = c.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": cid,
                "code": code,
                "redirect_uri": "https://app.local/callback",
                "code_verifier": verifier,
            },
        )
        assert token_resp.status_code == 200, token_resp.text
        tokens = token_resp.json()
        assert tokens["token_type"] == "Bearer"
        assert tokens["access_token"]
        assert tokens["refresh_token"]

        refresh_resp = c.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": cid,
                "refresh_token": tokens["refresh_token"],
            },
        )
        assert refresh_resp.status_code == 200, refresh_resp.text
        rotated = refresh_resp.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]


def test_token_endpoint_rejects_unsupported_grant() -> None:
    cid = f"http-c3-{secrets.token_hex(3)}"
    _seed_client(cid)
    with TestClient(app) as c:
        r = c.post(
            "/oauth/token",
            data={"grant_type": "password", "client_id": cid},
        )
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


def test_token_endpoint_rejects_pkce_failure() -> None:
    cid = f"http-c4-{secrets.token_hex(3)}"
    _seed_client(cid)
    verifier = "v" * 64
    with TestClient(app) as c:
        auth = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://app.local/callback",
                "code_challenge": _challenge(verifier),
                "code_challenge_method": "S256",
                "user_subject": "u",
            },
            follow_redirects=False,
        )
        code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]
        bad = c.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": cid,
                "code": code,
                "redirect_uri": "https://app.local/callback",
                "code_verifier": "WRONG_VERIFIER_VALUE_DEFINITELY_NOT_MATCH",
            },
        )
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_grant"
