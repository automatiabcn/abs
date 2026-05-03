"""T-003 — OAuth 2.1 server core.

Issues authorization codes, exchanges them for JWT access tokens, rotates
opaque refresh tokens. PKCE S256 is mandatory; refresh tokens are
single-use (rotation chain on `rotated_to_hash`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.auth.oauth.jwks import (
    current_kid,
    private_signing_key,
    public_verification_key,
)
from app.auth.oauth.models import OAuthAuthCode, OAuthClient, OAuthRefreshToken
from app.auth.oauth.pkce import verify_s256
from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "OAuthError",
    "exchange_code_for_tokens",
    "issue_authorization_code",
    "refresh_access_token",
    "verify_access_token",
]

ACCESS_TOKEN_TTL = timedelta(minutes=15)
AUTH_CODE_TTL = timedelta(minutes=2)
REFRESH_TOKEN_TTL = timedelta(days=30)
DEFAULT_ISSUER = "https://abs.local"


class OAuthError(Exception):
    """RFC 6749 §5.2 error wrapper."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(description or code)
        self.code = code
        self.description = description


def _now() -> datetime:
    """UTC-naive timestamp (matches SQLite default datetime storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issuer() -> str:
    return getattr(settings, "oauth_issuer", DEFAULT_ISSUER)


def _revoke_refresh_family(db: Session, start_hash: str) -> int:
    """OAuth 2.1 §6.1 — on detected refresh-token replay, revoke the entire
    rotation chain (forward from `start_hash`). Returns count revoked."""
    from app.db.query_helpers import first_or_none

    chain: list[str] = []
    cursor: str | None = start_hash
    while cursor and cursor not in chain:
        chain.append(cursor)
        nxt = first_or_none(
            db,
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.token_hash == cursor
            ),
        )
        cursor = nxt.rotated_to_hash if nxt is not None else None
    if not chain:
        return 0
    now = _now()
    revoke_stmt = (
        sa_update(OAuthRefreshToken)
        .where(OAuthRefreshToken.token_hash.in_(chain))
        .where(OAuthRefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    res = db.execute(revoke_stmt)
    db.commit()
    return int(res.rowcount or 0)


def _client_or_raise(db: Session, client_id: str) -> OAuthClient:
    from app.db.query_helpers import first_or_none

    client = first_or_none(
        db, select(OAuthClient).where(OAuthClient.client_id == client_id)
    )
    if client is None or client.revoked_at is not None:
        raise OAuthError("invalid_client", f"unknown client {client_id}")
    return client


def _check_client_secret(client: OAuthClient, client_secret: str | None) -> None:
    if not client.is_confidential:
        return
    if not client_secret or not client.client_secret_hash:
        raise OAuthError("invalid_client", "client authentication required")
    ok = bcrypt.checkpw(
        client_secret.encode("utf-8"),
        client.client_secret_hash.encode("utf-8"),
    )
    if not ok:
        raise OAuthError("invalid_client", "client secret mismatch")


def _check_redirect(client: OAuthClient, redirect_uri: str) -> None:
    allow = [u.strip() for u in client.redirect_uris.splitlines() if u.strip()]
    if redirect_uri not in allow:
        raise OAuthError(
            "invalid_request", f"redirect_uri {redirect_uri!r} not registered"
        )


RESERVED_CLAIMS = {
    "iss",
    "sub",
    "aud",
    "iat",
    "exp",
    "jti",
    "scope",
    "token_use",
}


def _sanitize_claims(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return {}
    return {k: v for k, v in extra.items() if k not in RESERVED_CLAIMS}


def issue_authorization_code(
    db: Session,
    *,
    client_id: str,
    user_subject: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str = "S256",
    scope: str = "",
    nonce: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> OAuthAuthCode:
    if code_challenge_method != "S256":
        raise OAuthError(
            "invalid_request",
            "OAuth 2.1 mandates code_challenge_method=S256",
        )
    client = _client_or_raise(db, client_id)
    _check_redirect(client, redirect_uri)

    now = _now()
    record = OAuthAuthCode(
        code=secrets.token_urlsafe(32),
        client_id=client_id,
        user_subject=user_subject,
        redirect_uri=redirect_uri,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        extra_claims_json=json.dumps(_sanitize_claims(extra_claims)),
        issued_at=now,
        expires_at=now + AUTH_CODE_TTL,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _mint_access_token(
    *,
    subject: str,
    client_id: str,
    scope: str,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    now = _now()
    expires = now + ACCESS_TOKEN_TTL
    payload: dict[str, Any] = {
        "iss": _issuer(),
        "sub": subject,
        "aud": client_id,
        "iat": _epoch(now),
        "exp": _epoch(expires),
        "jti": secrets.token_urlsafe(16),
        "scope": scope,
        "token_use": "access",
    }
    payload.update(_sanitize_claims(extra_claims))
    token = jwt.encode(
        payload,
        private_signing_key(),
        algorithm="RS256",
        headers={"kid": current_kid()},
    )
    return token, int(ACCESS_TOKEN_TTL.total_seconds())


def _mint_refresh_token(
    db: Session,
    *,
    client_id: str,
    subject: str,
    scope: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    raw = secrets.token_urlsafe(48)
    now = _now()
    db.add(
        OAuthRefreshToken(
            token_hash=_hash_token(raw),
            client_id=client_id,
            user_subject=subject,
            scope=scope,
            extra_claims_json=json.dumps(_sanitize_claims(extra_claims)),
            issued_at=now,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
    )
    db.commit()
    return raw


def exchange_code_for_tokens(
    db: Session,
    *,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_secret: str | None = None,
) -> dict:
    client = _client_or_raise(db, client_id)
    _check_client_secret(client, client_secret)
    _check_redirect(client, redirect_uri)

    from app.db.query_helpers import first_or_none

    record = first_or_none(
        db, select(OAuthAuthCode).where(OAuthAuthCode.code == code)
    )
    if record is None:
        raise OAuthError("invalid_grant", "unknown authorization code")
    if record.client_id != client_id:
        raise OAuthError("invalid_grant", "code/client mismatch")
    if record.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri mismatch")
    if record.used_at is not None:
        logger.warning("oauth_code_replay_attempt client_id=%s", client_id)
        raise OAuthError("invalid_grant", "code already used")
    if record.expires_at <= _now():
        raise OAuthError("invalid_grant", "code expired")
    if not verify_s256(code_verifier, record.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed")

    claim_now = _now()
    db.expire(record, ["used_at"])
    claim_stmt = (
        sa_update(OAuthAuthCode)
        .where(OAuthAuthCode.code == code)
        .where(OAuthAuthCode.used_at.is_(None))
        .values(used_at=claim_now)
    )
    claim_result = db.execute(claim_stmt)
    db.commit()
    if (claim_result.rowcount or 0) != 1:
        logger.warning(
            "oauth_code_replay_blocked client_id=%s — concurrent claim lost race",
            client_id,
        )
        raise OAuthError("invalid_grant", "code already used")
    db.refresh(record)

    extra = json.loads(record.extra_claims_json or "{}")
    access, ttl = _mint_access_token(
        subject=record.user_subject,
        client_id=client_id,
        scope=record.scope,
        extra_claims=extra,
    )
    refresh = _mint_refresh_token(
        db,
        client_id=client_id,
        subject=record.user_subject,
        scope=record.scope,
        extra_claims=extra,
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ttl,
        "refresh_token": refresh,
        "scope": record.scope,
    }


def refresh_access_token(
    db: Session,
    *,
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
) -> dict:
    client = _client_or_raise(db, client_id)
    _check_client_secret(client, client_secret)

    from app.db.query_helpers import first_or_none

    presented_hash = _hash_token(refresh_token)
    rt = first_or_none(
        db,
        select(OAuthRefreshToken).where(
            OAuthRefreshToken.token_hash == presented_hash
        ),
    )
    if rt is None:
        raise OAuthError("invalid_grant", "unknown refresh token")
    if rt.client_id != client_id:
        raise OAuthError("invalid_grant", "client mismatch")
    if rt.revoked_at is not None or rt.rotated_to_hash is not None:
        # Q12-L22-006 — OAuth 2.1 §6.1: replayed refresh token MUST trigger
        # family revocation. Walk forward chain + bulk-revoke.
        _revoke_refresh_family(db, presented_hash)
        logger.warning(
            "oauth_refresh_replay_blocked client_id=%s — family revoked", client_id
        )
        raise OAuthError("invalid_grant", "refresh token already used")
    if rt.expires_at <= _now():
        raise OAuthError("invalid_grant", "refresh token expired")

    new_raw = secrets.token_urlsafe(48)
    new_hash = _hash_token(new_raw)

    # Q12-L22-006 — atomic rotation claim. Two concurrent refreshes with the
    # same token race on read-then-write of rotated_to_hash; only one wins.
    db.expire(rt, ["rotated_to_hash", "revoked_at"])
    rotate_stmt = (
        sa_update(OAuthRefreshToken)
        .where(OAuthRefreshToken.token_hash == presented_hash)
        .where(OAuthRefreshToken.rotated_to_hash.is_(None))
        .where(OAuthRefreshToken.revoked_at.is_(None))
        .values(rotated_to_hash=new_hash)
    )
    rotate_result = db.execute(rotate_stmt)
    if (rotate_result.rowcount or 0) != 1:
        db.rollback()
        # Lost the race: treat as replay → revoke family.
        _revoke_refresh_family(db, presented_hash)
        logger.warning(
            "oauth_refresh_race_blocked client_id=%s — family revoked", client_id
        )
        raise OAuthError("invalid_grant", "refresh token already used")
    db.add(
        OAuthRefreshToken(
            token_hash=new_hash,
            client_id=client_id,
            user_subject=rt.user_subject,
            scope=rt.scope,
            extra_claims_json=rt.extra_claims_json,
            issued_at=_now(),
            expires_at=_now() + REFRESH_TOKEN_TTL,
        )
    )
    db.commit()
    db.refresh(rt)

    extra = json.loads(rt.extra_claims_json or "{}")
    access, ttl = _mint_access_token(
        subject=rt.user_subject,
        client_id=client_id,
        scope=rt.scope,
        extra_claims=extra,
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ttl,
        "refresh_token": new_raw,
        "scope": rt.scope,
    }


def verify_access_token(token: str, *, audience: str | None = None) -> dict:
    """Verify an issued access token. Returns claims dict on success."""
    try:
        return jwt.decode(
            token,
            public_verification_key(),
            algorithms=["RS256"],
            audience=audience,
            issuer=_issuer(),
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.InvalidTokenError as exc:
        raise OAuthError("invalid_token", str(exc)) from exc
