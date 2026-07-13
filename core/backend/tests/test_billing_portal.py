"""017 — POST /v1/billing/portal: Stripe Customer Portal session."""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.config import settings
from app.db.models import License
from app.db.session import get_engine


@pytest.fixture()
def _seed_active_license():
    """Aktif lisans ekle (revoked_at IS NULL, customer_id_stripe='cus_portal_1')."""
    now = datetime.now(timezone.utc)
    row = License(
        jti="jti_portal_active",
        customer_email="active@x.co",
        customer_id_stripe="cus_portal_1",
        tier="self-host",
        seat_count=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )
    with Session(get_engine()) as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


@pytest.fixture()
def _seed_revoked_license():
    now = datetime.now(timezone.utc)
    row = License(
        jti="jti_portal_revoked",
        customer_email="revoked@x.co",
        customer_id_stripe="cus_portal_revoked",
        tier="self-host",
        seat_count=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
        revoked_at=now,
        revoked_reason="stripe_refund",
    )
    with Session(get_engine()) as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


def test_portal_no_stripe_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    r = client.post("/v1/billing/portal", json={"customer_email": "a@b.co"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


def test_portal_no_active_license_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    r = client.post("/v1/billing/portal", json={"customer_email": "missing@x.co"})
    assert r.status_code == 404


def test_portal_active_license_returns_url(client, monkeypatch, _seed_active_license):
    """Aktif lisans + Stripe API mock → portal URL."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")

    fake_portal = types.SimpleNamespace(
        url="https://billing.stripe.com/test_xyz_session", id="bps_test_1"
    )

    def _fake_create(**kwargs):
        assert kwargs["customer"] == "cus_portal_1"
        return fake_portal

    monkeypatch.setattr("stripe.billing_portal.Session.create", _fake_create)

    r = client.post("/v1/billing/portal", json={"customer_email": "active@x.co"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "billing.stripe.com" in body["portal_url"]
    assert body["expires_at"]


def test_portal_revoked_license_returns_404(client, monkeypatch, _seed_revoked_license):
    """Revoked lisans → portal kapalı (refund sonrası)."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    r = client.post("/v1/billing/portal", json={"customer_email": "revoked@x.co"})
    assert r.status_code == 404
