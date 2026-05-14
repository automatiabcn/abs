"""Sprint 2I UAT-027 — beta license expires_at post-check + 7-day grace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine
from app.licensing import (
    LicenseStatus,
    generate_license,
    license_grace_status,
    verify_license_with_grace,
)


def _seed_license(*, days_offset: int):
    """Issue a license + persist a License row whose ``expires_at`` is
    ``days_offset`` days from now (negative = already expired)."""
    token = generate_license(f"uat027-{days_offset}", valid_days=365 * 5)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            row = License(
                jti=jti,
                customer_email="grace@example.com",
                customer_id_stripe="cus_x",
                tier="beta",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=days_offset),
            )
        else:
            row.expires_at = now + timedelta(days=days_offset)
        db.add(row)
        db.commit()
    return token, jti


def test_active_license_returns_active_status():
    token, _ = _seed_license(days_offset=10)
    payload, st = verify_license_with_grace(token)
    assert st is LicenseStatus.ACTIVE
    assert payload["jti"]


def test_expired_within_grace_returns_pending():
    token, _ = _seed_license(days_offset=-3)
    payload, st = verify_license_with_grace(token)
    assert st is LicenseStatus.EXPIRED_PENDING_GRACE
    assert payload["jti"]


def test_expired_past_grace_raises_401():
    token, _ = _seed_license(days_offset=-30)
    with pytest.raises(HTTPException) as info:
        verify_license_with_grace(token)
    assert info.value.status_code == 401
    assert info.value.detail == "license_expired_grace_elapsed"


def test_status_helper_handles_missing_license_row():
    """Defensive — the JWT itself is enough; the grace check is best-effort."""
    payload = {"jti": "definitely-not-in-db-uuid"}
    assert license_grace_status(payload) is LicenseStatus.ACTIVE
