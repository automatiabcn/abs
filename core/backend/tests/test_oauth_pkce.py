"""PKCE + JWKS unit tests."""

from __future__ import annotations

import base64
import hashlib

from app.auth.oauth.jwks import current_kid, jwks_document
from app.auth.oauth.pkce import verify_s256


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def test_pkce_s256_accepts_valid_pair() -> None:
    v = "a" * 43
    assert verify_s256(v, _challenge(v)) is True


def test_pkce_s256_rejects_mismatch() -> None:
    v = "a" * 43
    assert verify_s256(v, "definitely-not-the-hash") is False


def test_pkce_s256_rejects_short_verifier() -> None:
    assert verify_s256("short", _challenge("short")) is False


def test_pkce_s256_rejects_long_verifier() -> None:
    v = "a" * 200
    assert verify_s256(v, _challenge(v)) is False


def test_pkce_s256_rejects_empty() -> None:
    assert verify_s256("", "") is False


def test_jwks_document_shape() -> None:
    doc = jwks_document()
    assert "keys" in doc and len(doc["keys"]) == 1
    key = doc["keys"][0]
    for required in ("kty", "use", "alg", "kid", "n", "e"):
        assert required in key
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert key["kty"] == "RSA"


def test_jwks_kid_is_stable_across_calls() -> None:
    assert current_kid() == current_kid()
    assert jwks_document()["keys"][0]["kid"] == current_kid()
