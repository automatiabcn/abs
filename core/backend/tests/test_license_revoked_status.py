"""022 Modul F — License GET /v1/license/status revoked_at raporu."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.config import settings
from app.db.models import License
from app.db.session import get_engine
from app.licensing import generate_license, verify_license


def _seed_revoked_license_and_settings(monkeypatch, jti_label: str = "rev_st"):
    token = generate_license(
        customer_id=f"cus_{jti_label}", tier="self-host", seat_count=1
    )
    payload = verify_license(token)
    jti = payload["jti"]

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        from sqlmodel import select

        existing = s.scalars(select(License).where(License.jti == jti)).first()
        if existing is None:
            s.add(
                License(
                    jti=jti,
                    customer_email=f"{jti_label}@x.co",
                    customer_id_stripe=f"cus_{jti_label}",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now,
                    expires_at=now + timedelta(days=365),
                    revoked_at=now,
                    revoked_reason="stripe_refund",
                )
            )
            s.commit()
        else:
            existing.revoked_at = now
            existing.revoked_reason = "stripe_refund"
            s.add(existing)
            s.commit()
    monkeypatch.setattr(settings, "license_key", token)
    return jti


def test_license_status_returns_revoked_for_revoked_db_row(client, monkeypatch):
    jti = _seed_revoked_license_and_settings(monkeypatch)
    r = client.get("/v1/license/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "revoked"
    assert body["jti"] == jti
    assert body["reason"] == "stripe_refund"
    assert "revoked_at" in body


def test_license_status_returns_active_when_no_revocation(client, monkeypatch):
    """Revoked olmayan lisans için status 'active'."""
    token = generate_license(
        customer_id="cus_active_st", tier="self-host", seat_count=1
    )
    monkeypatch.setattr(settings, "license_key", token)
    r = client.get("/v1/license/status")
    assert r.status_code == 200
    assert r.json()["status"] == "active"
