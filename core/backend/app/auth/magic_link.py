# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""magic-link token helper.

Used by the admin invite flow (`POST /v1/admin/users/invite`) and the
matching consume-side endpoint (`/auth/magic`). The token plaintext is
mailed to the recipient; only an HMAC-SHA256 digest of the token is
persisted (`tenant_invites.magic_token_hash`). When the recipient hits
`/auth/magic?token=<plaintext>` the consumer recomputes the digest and
looks up the row — so a database read can never recover a usable token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Tuple

from app.config import settings

Purpose = Literal["login", "invite"]

DEFAULT_TTL_MINUTES: int = 60 * 24 * 7  # 7 days
TOKEN_BYTES: int = 32


def _hmac_secret() -> bytes:
    raw = (settings.magic_link_hmac_secret or "").strip()
    if not raw:
        # Defense-in-depth: never fall back to an empty key (would make
        # all hashes deterministic and trivially forgeable). Reuse the
        # admin JWT secret as a stable per-install fallback so dev /
        # tests don't have to set the env var explicitly.
        raw = settings.admin_jwt_secret
    return raw.encode("utf-8")


def _hash(plaintext: str) -> str:
    digest = hmac.new(_hmac_secret(), plaintext.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def create_magic_link_token(
    email: str,
    tenant_id: str,
    *,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    purpose: Purpose = "login",
) -> Tuple[str, str, datetime]:
    """Generate a fresh magic-link token.

    Returns ``(plaintext_token, hash, expires_at)``. The plaintext goes
    into the URL emailed to the user; the hash is stored in the DB.
    """
    if not email or not tenant_id:
        raise ValueError("email and tenant_id required")
    if ttl_minutes <= 0:
        raise ValueError("ttl_minutes must be positive")
    if purpose not in ("login", "invite"):
        raise ValueError("purpose must be 'login' or 'invite'")

    plaintext = secrets.token_urlsafe(TOKEN_BYTES)
    digest = _hash(plaintext)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    return plaintext, digest, expires_at


def hash_magic_token(plaintext: str) -> str:
    """Return the HMAC digest for an existing token (consume-side)."""
    if not plaintext:
        raise ValueError("plaintext required")
    return _hash(plaintext)


def verify_magic_token(
    plaintext: str,
    stored_hash: str,
    expires_at: datetime,
    *,
    purpose: Purpose,
    expected_purpose: Purpose,
) -> bool:
    """Constant-time check: plaintext digest matches stored hash, not
    expired, and the row's purpose matches what the caller expects.

    Returns ``True`` only when all three hold; otherwise ``False`` so the
    caller can return a generic 410/404 without revealing which check
    failed.
    """
    if not plaintext or not stored_hash:
        return False
    if purpose != expected_purpose:
        return False
    if expires_at is None:
        return False
    # SQLite drops timezone on round-trip; treat naive as UTC.
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return False
    candidate = _hash(plaintext)
    return hmac.compare_digest(candidate, stored_hash)


__all__ = [
    "Purpose",
    "DEFAULT_TTL_MINUTES",
    "create_magic_link_token",
    "hash_magic_token",
    "verify_magic_token",
]
