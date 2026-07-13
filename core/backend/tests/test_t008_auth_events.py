"""T-008 — Auth lifecycle events (NATS publish + OAuth route emission)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth import events
from app.auth.oauth import routes as oauth_routes
from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
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


def test_event_subjects_mapping_is_canonical() -> None:
    assert events.EVENT_SUBJECTS == {
        "user.registered": "abs.events.user.registered",
        "user.login.success": "abs.events.user.login.success",
        "user.login.failed": "abs.events.user.login.failed",
    }


async def test_publish_user_registered_envelope_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = AsyncMock(return_value=42)
    monkeypatch.setattr(events, "nats_publish", bus)

    seq = await events.publish_user_registered("u1", email="a@b.c", tenant_id="t1")
    assert seq == "42"
    subject, envelope = bus.call_args.args
    assert subject == "abs.events.user.registered"
    assert envelope["schema_version"] == 1
    assert envelope["event_type"] == "user.registered"
    assert envelope["source"] == "abs-backend"
    assert envelope["data"] == {
        "user_id": "u1",
        "email": "a@b.c",
        "source": "oauth",
        "tenant_id": "t1",
    }
    assert envelope["metadata"] == {}
    assert envelope["occurred_at"].endswith("Z")
    assert "T" in envelope["occurred_at"]


async def test_publish_login_success_includes_scope_and_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = AsyncMock(return_value=7)
    monkeypatch.setattr(events, "nats_publish", bus)

    seq = await events.publish_login_success(
        "u2",
        client_id="c1",
        tenant_id="t1",
        scope="rag:query",
        metadata={"jti": "x"},
    )
    assert seq == "7"
    subject, envelope = bus.call_args.args
    assert subject == "abs.events.user.login.success"
    assert envelope["data"] == {
        "user_id": "u2",
        "client_id": "c1",
        "tenant_id": "t1",
        "scope": "rag:query",
    }
    assert envelope["metadata"] == {"jti": "x"}


async def test_publish_login_failed_omits_subject_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = AsyncMock(return_value=99)
    monkeypatch.setattr(events, "nats_publish", bus)

    seq = await events.publish_login_failed(client_id="c2", reason="bad_password")
    assert seq == "99"
    _, envelope = bus.call_args.args
    data = envelope["data"]
    assert "user_subject" not in data
    assert data["client_id"] == "c2"
    assert data["reason"] == "bad_password"
    assert data["error_code"] == "invalid_grant"


async def test_publish_login_failed_includes_subject_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = AsyncMock(return_value=101)
    monkeypatch.setattr(events, "nats_publish", bus)

    seq = await events.publish_login_failed(
        client_id="c3",
        reason="account_locked",
        user_subject="alice",
        error_code="invalid_grant",
    )
    assert seq == "101"
    _, envelope = bus.call_args.args
    assert envelope["data"]["user_subject"] == "alice"


async def test_publish_returns_empty_string_on_bus_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_error(*_args, **_kwargs):
        raise ConnectionError("bus down")

    monkeypatch.setattr(events, "nats_publish", raise_error)

    seq = await events.publish_user_registered("u3", email="x@y.z")
    assert seq == ""


def test_token_endpoint_emits_login_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = f"evt-{secrets.token_hex(3)}"
    _seed_client(client_id)

    mock_success = AsyncMock()
    monkeypatch.setattr(oauth_routes, "publish_login_success", mock_success)
    monkeypatch.setattr(oauth_routes, "publish_login_failed", AsyncMock())

    verifier = "v" * 64
    with TestClient(app) as c:
        auth = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://app.local/callback",
                "code_challenge": _challenge(verifier),
                "code_challenge_method": "S256",
                "scope": "openid profile",
                "user_subject": "alice",
                "tenant_id": "tenant-1",
                "roles": "member",
            },
            follow_redirects=False,
        )
        assert auth.status_code == 302
        code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]

        tok = c.post(
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
    mock_success.assert_awaited_once()
    kwargs = mock_success.call_args.kwargs
    assert kwargs["client_id"] == client_id
    assert kwargs["user_id"] == "alice"
    assert kwargs["tenant_id"] == "tenant-1"


def test_token_endpoint_emits_login_failed_on_unsupported_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = f"evt-{secrets.token_hex(3)}"
    _seed_client(client_id)

    mock_failed = AsyncMock()
    monkeypatch.setattr(oauth_routes, "publish_login_failed", mock_failed)
    monkeypatch.setattr(oauth_routes, "publish_login_success", AsyncMock())

    with TestClient(app) as c:
        r = c.post(
            "/oauth/token",
            data={"grant_type": "password", "client_id": client_id},
        )
    assert r.status_code == 400
    mock_failed.assert_awaited_once()
    kwargs = mock_failed.call_args.kwargs
    assert kwargs["error_code"] == "unsupported_grant_type"
    assert kwargs["client_id"] == client_id


def test_token_endpoint_emits_login_failed_on_pkce_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = f"evt-{secrets.token_hex(3)}"
    _seed_client(client_id)

    mock_failed = AsyncMock()
    monkeypatch.setattr(oauth_routes, "publish_login_failed", mock_failed)
    monkeypatch.setattr(oauth_routes, "publish_login_success", AsyncMock())

    verifier = "v" * 64
    with TestClient(app) as c:
        auth = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
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
                "client_id": client_id,
                "code": code,
                "redirect_uri": "https://app.local/callback",
                "code_verifier": "WRONG_VERIFIER_VALUE_DOES_NOT_MATCH",
            },
        )
    assert bad.status_code == 400
    mock_failed.assert_awaited_once()
    kwargs = mock_failed.call_args.kwargs
    assert kwargs["error_code"] == "invalid_grant"
