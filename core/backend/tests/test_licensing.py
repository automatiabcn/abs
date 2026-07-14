"""Licensing generator + verifier edge case'leri."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.licensing import generate_license, verify_license


def test_generate_and_verify_roundtrip():
    token = generate_license("cust_1", tier="team", seat_count=5, valid_days=30)
    payload = verify_license(token)

    assert payload["customer_id"] == "cust_1"
    assert payload["tier"] == "team"
    assert payload["seat_count"] == 5
    assert "jti" in payload and len(payload["jti"]) >= 16
    assert payload["exp"] > payload["iat"]


def test_expired_license_rejected():
    token = generate_license("cust_2", valid_days=-1)
    with pytest.raises(HTTPException) as exc_info:
        verify_license(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_tampered_signature_rejected():
    token = generate_license("cust_3")
    # invalidate the signature by corrupting the last 10 characters
    tampered = token[:-10] + ("A" * 10)
    with pytest.raises(HTTPException) as exc_info:
        verify_license(tampered)
    assert exc_info.value.status_code in (400, 401)


def test_malformed_token_rejected():
    with pytest.raises(HTTPException) as exc_info:
        verify_license("not.a.valid.token")
    assert exc_info.value.status_code == 400
