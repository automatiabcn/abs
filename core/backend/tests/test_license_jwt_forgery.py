"""Adversarial: attempt to forge a license past verify_license().

The license JWT gates the whole product, so the verifier must resist the
classic JWT attacks. Each forgery below MUST be rejected (HTTPException);
test_valid_token_passes is the control proving a legit token still works.
"""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.licensing.keys import load_private_key, load_public_key
from app.licensing.verifier import verify_license


def _claims(**over):
    now = int(time.time())
    base = {"sub": "cust-1", "iat": now, "exp": now + 3600, "jti": "test-jti-1"}
    base.update(over)
    return base


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_valid_token_passes():
    priv = load_private_key(settings.private_key_path)
    token = jwt.encode(_claims(), priv, algorithm="RS256")
    payload = verify_license(token)
    assert payload["jti"] == "test-jti-1"


def test_alg_none_rejected():
    # Unsigned token with alg=none — crafted manually since PyJWT won't mint it.
    header = _b64({"alg": "none", "typ": "JWT"})
    body = _b64(_claims())
    forged = f"{header}.{body}."
    with pytest.raises(HTTPException):
        verify_license(forged)


def test_rs_hs_alg_confusion_rejected():
    # Classic RS/HS confusion: sign HS256 using the PUBLIC key as the HMAC
    # secret. Modern PyJWT refuses to *encode* this, so we craft the token by
    # hand to truly exercise the verifier's algorithm pinning (algorithms=
    # ["RS256"]) — a verifier that didn't pin would accept this forgery.
    import hashlib
    import hmac

    pub = load_public_key(settings.public_key_path)
    header = _b64({"alg": "HS256", "typ": "JWT"})
    body = _b64(_claims())
    signing_input = f"{header}.{body}".encode()
    sig = (
        base64.urlsafe_b64encode(hmac.new(pub, signing_input, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    forged = f"{header}.{body}.{sig}"
    with pytest.raises(HTTPException):
        verify_license(forged)


def test_wrong_signing_key_rejected(tmp_path):
    # Token signed by a DIFFERENT private key → signature must not verify.
    from app.licensing.keys import generate_keypair

    p2 = tmp_path / "p2.pem"
    pub2 = tmp_path / "pub2.pem"
    generate_keypair(str(p2), str(pub2))
    attacker_priv = load_private_key(str(p2))
    forged = jwt.encode(_claims(), attacker_priv, algorithm="RS256")
    with pytest.raises(HTTPException):
        verify_license(forged)


def test_missing_jti_rejected():
    priv = load_private_key(settings.private_key_path)
    claims = _claims()
    del claims["jti"]
    token = jwt.encode(claims, priv, algorithm="RS256")
    with pytest.raises(HTTPException):
        verify_license(token)


def test_tampered_payload_rejected():
    priv = load_private_key(settings.private_key_path)
    token = jwt.encode(_claims(sub="cust-1"), priv, algorithm="RS256")
    header, body, sig = token.split(".")
    tampered_body = _b64(_claims(sub="admin-elevated"))
    forged = f"{header}.{tampered_body}.{sig}"
    with pytest.raises(HTTPException):
        verify_license(forged)


def test_expired_token_rejected():
    priv = load_private_key(settings.private_key_path)
    token = jwt.encode(_claims(exp=int(time.time()) - 10), priv, algorithm="RS256")
    with pytest.raises(HTTPException):
        verify_license(token)
