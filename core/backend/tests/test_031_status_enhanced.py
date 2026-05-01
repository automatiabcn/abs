"""031 Modul D — Enhanced status + admin /v1/admin/status/full."""

from __future__ import annotations

from app.config import settings


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {settings.beta_admin_token}"}


def test_public_status_minimal_shape(client):
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    for key in ("overall", "uptime_seconds", "version", "services"):
        assert key in body
    # Public status MUST NOT leak admin counters
    assert "mrr_estimate_usd" not in body
    assert "licenses_active" not in body


def test_admin_status_requires_bearer(client):
    r = client.get("/v1/admin/status/full")
    assert r.status_code == 401
    r = client.get(
        "/v1/admin/status/full", headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 403


def test_admin_status_full_shape(client):
    r = client.get("/v1/admin/status/full", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    for key in (
        "overall",
        "services",
        "licenses_active",
        "mrr_estimate_usd",
        "signups_24h",
        "last_payment_at",
    ):
        assert key in body, f"missing key: {key}"
    assert isinstance(body["licenses_active"], int)
    assert isinstance(body["mrr_estimate_usd"], int)
    assert isinstance(body["signups_24h"], int)


def test_admin_status_counts_are_non_negative(client):
    r = client.get("/v1/admin/status/full", headers=_admin_headers())
    body = r.json()
    assert body["licenses_active"] >= 0
    assert body["mrr_estimate_usd"] >= 0
    assert body["signups_24h"] >= 0
