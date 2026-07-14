"""Polish round R6 — /v1/license/info combines /status + /demo-status.

The Settings → Lisans tab in the admin UI fetches this single endpoint to
render every field (status, tier, jti, seat_count, expires_at, customer_id,
demo block). Hardcoded mock values were removed from the frontend, so any
shape regression here lights up the UI as "—".
"""

from __future__ import annotations

from app.config import settings
from app.licensing import generate_license

INFO_URL = "/v1/license/info"

REQUIRED_KEYS = {
    "status",
    "tier",
    "jti",
    "seat_count",
    "expires_at",
    "customer_id",
    "demo",
}


def test_license_info_trial_branch_when_no_key(client):
    """No configured key → the seven-day trial, with the countdown inlined.

    It used to say "demo" and mean fourteen days. The product is a monthly
    subscription now, the free window is a trial, and there is only one of it.
    """
    settings.license_key = ""

    r = client.get(INFO_URL)
    assert r.status_code == 200, r.text

    body = r.json()
    assert REQUIRED_KEYS.issubset(body), f"missing keys: {REQUIRED_KEYS - set(body)}"
    assert body["status"] == "trial"
    assert body["allowed"] is True
    assert 1 <= body["demo"]["days_remaining"] <= 7
    # All licensed fields are explicit nulls so the UI doesn't render
    # "undefined" or fall back to the old hardcoded mock.
    for field in ("tier", "jti", "seat_count", "expires_at", "customer_id"):
        assert body[field] is None, f"{field} should be None in demo branch"
    # Demo countdown is inlined so the UI doesn't need a second request.
    assert body["demo"] is not None
    assert isinstance(body["demo"], dict)


def test_license_info_licensed_branch(client):
    """Activated license → status=licensed plus the JWT claims, no mocks."""
    token = generate_license("cust_info_1", tier="self-host", seat_count=5)

    activate = client.post("/v1/license/activate", json={"license_key": token})
    assert activate.status_code == 200, activate.text

    r = client.get(INFO_URL)
    assert r.status_code == 200, r.text

    body = r.json()
    assert REQUIRED_KEYS.issubset(body)
    assert body["status"] == "licensed"
    assert body["tier"] == "self-host"
    assert body["seat_count"] == 5
    assert body["customer_id"] == "cust_info_1"
    assert body["jti"], "JTI must be non-empty when licensed"
    assert body["expires_at"], "expires_at must be ISO-8601 when licensed"
    # Demo block is suppressed when a real license is loaded.
    assert body["demo"] is None

    # Cleanup so neighbour tests don't see a stale runtime key.
    settings.license_key = ""


def test_license_info_invalid_key_branch(client):
    """Garbage key in settings → status=invalid with nulled-out fields."""
    settings.license_key = "not.a.valid.jwt"

    r = client.get(INFO_URL)
    assert r.status_code == 200, r.text

    body = r.json()
    assert REQUIRED_KEYS.issubset(body)
    assert body["status"] in {"invalid", "expired"}
    # The endpoint should still return the canonical shape so the UI's
    # destructure doesn't crash on the error branch.
    for field in ("tier", "jti", "seat_count", "expires_at", "customer_id"):
        assert body[field] is None

    settings.license_key = ""
