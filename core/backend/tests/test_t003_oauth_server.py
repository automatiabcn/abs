"""T-003 — OAuth 2.1 server unit tests (DB-backed)."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

import bcrypt
import jwt
import pytest
from sqlmodel import Session

from app.auth.oauth import server as oauth_server
from app.auth.oauth.jwks import public_verification_key
from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


@pytest.fixture()
def db_session():
    with Session(get_engine()) as session:
        yield session


def _seed_client(
    db: Session,
    *,
    client_id: str = "abs-cli",
    confidential: bool = False,
    secret: str | None = None,
    redirects: str = "https://app.local/callback",
) -> OAuthClient:
    secret_hash: str | None = None
    if secret:
        secret_hash = bcrypt.hashpw(
            secret.encode("utf-8"), bcrypt.gensalt(rounds=4)
        ).decode("utf-8")
    client = OAuthClient(
        client_id=client_id,
        client_secret_hash=secret_hash,
        is_confidential=confidential,
        redirect_uris=redirects,
        allowed_scopes="openid profile",
        created_at=datetime.now(timezone.utc),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def test_issue_code_rejects_unregistered_redirect(db_session: Session) -> None:
    _seed_client(db_session, client_id="c1")
    verifier = "v" * 64
    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.issue_authorization_code(
            db_session,
            client_id="c1",
            user_subject="user-1",
            redirect_uri="https://evil.example/cb",
            code_challenge=_challenge(verifier),
        )
    assert exc.value.code == "invalid_request"


def test_issue_code_rejects_plain_method(db_session: Session) -> None:
    _seed_client(db_session, client_id="c2")
    with pytest.raises(oauth_server.OAuthError):
        oauth_server.issue_authorization_code(
            db_session,
            client_id="c2",
            user_subject="user-1",
            redirect_uri="https://app.local/callback",
            code_challenge="x",
            code_challenge_method="plain",
        )


def test_authorization_code_flow_end_to_end(db_session: Session) -> None:
    _seed_client(
        db_session,
        client_id="c3",
        confidential=True,
        secret="topsecret",
    )
    verifier = "v" * 64

    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c3",
        user_subject="user-42",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
        scope="openid profile",
    )

    tokens = oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="c3",
        code=code.code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
        client_secret="topsecret",
    )
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] > 0
    assert tokens["refresh_token"]
    assert tokens["scope"] == "openid profile"

    decoded = jwt.decode(
        tokens["access_token"],
        public_verification_key(),
        algorithms=["RS256"],
        audience="c3",
        issuer="https://abs.local",
    )
    assert decoded["sub"] == "user-42"
    assert decoded["scope"] == "openid profile"
    assert decoded["token_use"] == "access"


def test_code_exchange_rejects_pkce_mismatch(db_session: Session) -> None:
    _seed_client(db_session, client_id="c4")
    verifier = "v" * 64

    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c4",
        user_subject="u",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
    )

    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.exchange_code_for_tokens(
            db_session,
            client_id="c4",
            code=code.code,
            redirect_uri="https://app.local/callback",
            code_verifier="WRONG_VERIFIER",
        )
    assert exc.value.code == "invalid_grant"


def test_code_replay_is_blocked(db_session: Session) -> None:
    _seed_client(db_session, client_id="c5")
    verifier = "v" * 64
    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c5",
        user_subject="u",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
    )
    oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="c5",
        code=code.code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.exchange_code_for_tokens(
            db_session,
            client_id="c5",
            code=code.code,
            redirect_uri="https://app.local/callback",
            code_verifier=verifier,
        )
    assert exc.value.code == "invalid_grant"


def test_confidential_client_requires_secret(db_session: Session) -> None:
    _seed_client(
        db_session,
        client_id="c6",
        confidential=True,
        secret="hunter2",
    )
    verifier = "v" * 64
    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c6",
        user_subject="u",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
    )
    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.exchange_code_for_tokens(
            db_session,
            client_id="c6",
            code=code.code,
            redirect_uri="https://app.local/callback",
            code_verifier=verifier,
        )
    assert exc.value.code == "invalid_client"


def test_refresh_token_rotation(db_session: Session) -> None:
    _seed_client(db_session, client_id="c7")
    verifier = "v" * 64
    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c7",
        user_subject="user-7",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
    )
    first = oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="c7",
        code=code.code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    second = oauth_server.refresh_access_token(
        db_session,
        client_id="c7",
        refresh_token=first["refresh_token"],
    )
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]

    # Old refresh token must be single-use (rotated).
    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.refresh_access_token(
            db_session,
            client_id="c7",
            refresh_token=first["refresh_token"],
        )
    assert exc.value.code == "invalid_grant"


def test_verify_access_token_round_trip(db_session: Session) -> None:
    _seed_client(db_session, client_id="c8")
    verifier = "v" * 64
    code = oauth_server.issue_authorization_code(
        db_session,
        client_id="c8",
        user_subject="user-8",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
        scope="rag:query",
    )
    tokens = oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="c8",
        code=code.code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    claims = oauth_server.verify_access_token(tokens["access_token"], audience="c8")
    assert claims["sub"] == "user-8"
    assert claims["scope"] == "rag:query"


def test_unknown_client_rejected(db_session: Session) -> None:
    with pytest.raises(oauth_server.OAuthError) as exc:
        oauth_server.issue_authorization_code(
            db_session,
            client_id="ghost",
            user_subject="u",
            redirect_uri="https://app.local/callback",
            code_challenge=_challenge("v" * 64),
        )
    assert exc.value.code == "invalid_client"
