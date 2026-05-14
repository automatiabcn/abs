"""Sprint 2I UAT-046 — Cerbos PDP unreachable surfaces HTTP 503 with
Retry-After (not 403, not 500) so clients retry instead of misreading
a transport blip as a permanent forbidden."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )


def _seed_client(client_id: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris="https://app.local/callback",
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()


def _issue_token(cli: TestClient, *, client_id: str) -> str:
    verifier = "v" * 64
    auth = cli.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": "alice",
            "tenant_id": "tenant-1",
            "roles": "member",
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302, auth.text
    code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]
    tok = cli.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"]


class _UnreachableCerbos:
    """Stand-in PDP that mimics a gRPC outage every call."""

    def check_resources(self, *, principal, resources):  # noqa: ANN001
        import grpc

        raise grpc.RpcError("UNAVAILABLE: connect failed")

    def close(self) -> None:
        pass


@pytest.fixture()
def install_unreachable_cerbos():
    app.state.cerbos_client = _UnreachableCerbos()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def test_pdp_unreachable_returns_503_with_retry_after(install_unreachable_cerbos):
    cid = f"gw-cu-{secrets.token_hex(3)}"
    _seed_client(cid)

    with TestClient(app) as c:
        token = _issue_token(c, client_id=cid)
        r = c.get(
            "/v1/projects/proj-t1-alice",
            headers={
                "Authorization": f"Bearer {token}",
                "X-ABS-Audience": cid,
            },
        )

    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "authorization_service_unavailable"
    assert r.headers.get("Retry-After") == "30"


def test_pdp_up_still_returns_200_baseline():
    """Regression — UAT-046 503 path must not regress the happy 200 path."""
    from types import SimpleNamespace

    class _UpCerbos:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            return SimpleNamespace(
                results=[SimpleNamespace(is_allowed=lambda _a: True)],
                failed=lambda: False,
                status_code=200,
            )

        def close(self) -> None:
            pass

    app.state.cerbos_client = _UpCerbos()
    try:
        cid = f"gw-cu-{secrets.token_hex(3)}"
        _seed_client(cid)
        with TestClient(app) as c:
            token = _issue_token(c, client_id=cid)
            r = c.get(
                "/v1/projects/proj-t1-alice",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-ABS-Audience": cid,
                },
            )
        assert r.status_code == 200, r.text
    finally:
        if hasattr(app.state, "cerbos_client"):
            delattr(app.state, "cerbos_client")
