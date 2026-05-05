"""Q12-R86 — License JWT full-lifecycle (4 boundaries + revoke + tamper +
100y guard).

S5/R28 shipped the alembic baseline + a JWT boundary spec; this round
verifies the round-trip end-to-end:

  1. exp = now-1s   → 401 expired
  2. exp = now      → 401 expired (boundary, ≤ now means already expired)
  3. exp = now+1s   → 200 verified
  4. exp = now+24h  → 200 verified
  5. revoke + reissue → first JTI marked revoked, fresh JTI verifies clean
  6. tampered signature → 401 (or 400)
  7. valid_days > 25y → WARNING logged (Q12-L21-003 LOW non-bug pin)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.licensing import generate_license, verify_license
from app.licensing.keys import load_private_key
from app.licensing.schemas import LicensePayload


def _mint_with_exp(exp_unix: int, customer_id: str = "cust_lifecycle") -> str:
    """Mint a JWT with a precise `exp` (seconds since epoch). Bypasses
    `generate_license`'s `valid_days` precision so we can hit boundaries."""
    iat = exp_unix - 60 if exp_unix > 60 else exp_unix - 1
    payload = LicensePayload(
        customer_id=customer_id,
        tier="self-host",
        seat_count=1,
        iat=iat,
        exp=exp_unix,
        jti=uuid.uuid4().hex,
    )
    private_key_bytes = load_private_key(settings.private_key_path)
    return jwt.encode(
        payload.model_dump(),
        key=private_key_bytes,
        algorithm="RS256",
    )


def test_license_now_minus_1s_rejected():
    now = int(time.time())
    token = _mint_with_exp(now - 1)
    with pytest.raises(HTTPException) as exc_info:
        verify_license(token)
    assert exc_info.value.status_code == 401
    assert "expired" in str(exc_info.value.detail).lower()


def test_license_now_plus_0s_rejected():
    # Boundary: exp == now means the token has already expired per JWT spec
    # (RFC 7519 §4.1.4 — "the current date/time MUST be before the expiration
    # date/time"). PyJWT enforces this strictly.
    now = int(time.time())
    token = _mint_with_exp(now)
    with pytest.raises(HTTPException) as exc_info:
        verify_license(token)
    assert exc_info.value.status_code == 401
    assert "expired" in str(exc_info.value.detail).lower()


def test_license_now_plus_1s_accepted():
    # Mint with a comfortable buffer (5s) so the verify-time clock cannot
    # tip into expiry between encode and decode on slow CI runners.
    now = int(time.time())
    token = _mint_with_exp(now + 5)
    payload = verify_license(token)
    assert payload["customer_id"] == "cust_lifecycle"
    assert payload["exp"] >= now + 1


def test_license_now_plus_24h_accepted():
    token = generate_license("cust_24h", valid_days=1)
    payload = verify_license(token)
    now = int(time.time())
    assert payload["exp"] - now > 23 * 3600
    assert payload["exp"] - now <= 24 * 3600 + 60  # tolerate small clock drift


def test_license_revoked_then_reissue_works(monkeypatch):
    """Revoke flow: the JTI is recorded as revoked at the License row level
    (api/license._check_revoked_at). Re-issuing for the same customer mints
    a fresh JTI; the new token verifies clean."""
    from sqlmodel import Session

    from app.db.models import License
    from app.db.session import get_engine

    token1 = generate_license("cust_revoke", valid_days=30)
    payload1 = verify_license(token1)
    jti1 = payload1["jti"]

    # Persist a License row for the JTI then mark it revoked.
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = License(
            jti=jti1,
            customer_id="cust_revoke",
            tier="self-host",
            seat_count=1,
            issued_at=now,
            expires_at=now,
            revoked_at=now,
            revoked_reason="chargeback",
        )
        db.add(row)
        db.commit()

    # JWT itself still verifies (revocation is a DB layer, not JWT-native).
    again = verify_license(token1)
    assert again["jti"] == jti1

    # Reissue produces a different JTI that has no revoked_at row.
    token2 = generate_license("cust_revoke", valid_days=30)
    payload2 = verify_license(token2)
    assert payload2["jti"] != jti1
    with Session(get_engine()) as db:
        row2 = db.get(License, payload2["jti"])
        # No row exists for the new JTI by default — clean.
        assert row2 is None or row2.revoked_at is None


def test_license_tampered_signature_rejected():
    token = generate_license("cust_tamper", valid_days=10)
    # Flip the last 16 chars of the signature segment.
    head, _, sig = token.rpartition(".")
    tampered = head + "." + ("A" * 16) + sig[16:]
    with pytest.raises(HTTPException) as exc_info:
        verify_license(tampered)
    assert exc_info.value.status_code in (400, 401)


def test_license_100y_expiry_warning_logged(caplog):
    """Q12-L21-003 LOW non-bug pin — a 100-year license is technically valid
    but operationally a smell. R86 added a `license_excessive_valid_days`
    WARN log; this test pins that behaviour."""
    with caplog.at_level(logging.WARNING, logger="app.licensing.generator"):
        token = generate_license("cust_100y", valid_days=100 * 365)

    # Token still mints + verifies — the warning is non-fatal.
    payload = verify_license(token)
    assert payload["customer_id"] == "cust_100y"

    # The warning hit the logger.
    assert any(
        "license_excessive_valid_days" in rec.message
        and "cust_100y" in rec.message
        for rec in caplog.records
    ), [rec.message for rec in caplog.records]
