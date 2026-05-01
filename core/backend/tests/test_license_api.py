"""POST /v1/license/activate + GET /v1/license/status."""

from __future__ import annotations

from app.config import settings
from app.licensing import generate_license


def test_status_unconfigured_returns_unconfigured(client):
    settings.license_key = ""
    r = client.get("/v1/license/status")
    assert r.status_code == 200
    assert r.json() == {"status": "unconfigured"}


def test_activate_then_status_shows_active(client):
    token = generate_license("cust_api_1", tier="team", seat_count=3)

    r = client.post("/v1/license/activate", json={"license_key": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "activated"
    assert body["tier"] == "team"
    assert body["seat_count"] == 3

    r2 = client.get("/v1/license/status")
    assert r2.status_code == 200
    status_body = r2.json()
    assert status_body["status"] == "active"
    assert status_body["tier"] == "team"
    assert status_body["seat_count"] == 3
    assert status_body["customer_id"] == "cust_api_1"


def test_activate_invalid_token_rejected(client):
    r = client.post(
        "/v1/license/activate",
        json={"license_key": "not.a.valid.jwt.token"},
    )
    assert r.status_code in (400, 401)
    # temizlik
    settings.license_key = ""
