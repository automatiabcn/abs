# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""JWKS export over the existing RSA license keypair.

Reuses settings.public_key_path / private_key_path so the same RSA pair
that signs licenses also signs OAuth access tokens. The key id (`kid`)
is a deterministic SHA-256 fingerprint of the DER public key.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.config import settings
from app.licensing.keys import load_private_key, load_public_key

__all__ = [
    "current_kid",
    "jwks_document",
    "private_signing_key",
    "public_verification_key",
]


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_object() -> RSAPublicKey:
    pem = load_public_key(settings.public_key_path)
    return serialization.load_pem_public_key(pem)  # type: ignore[return-value]


@lru_cache(maxsize=4)
def _kid_for(pub_pem: bytes) -> str:
    der = serialization.load_pem_public_key(pub_pem).public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()[:16]


def current_kid() -> str:
    return _kid_for(load_public_key(settings.public_key_path))


def private_signing_key() -> bytes:
    return load_private_key(settings.private_key_path)


def public_verification_key() -> bytes:
    return load_public_key(settings.public_key_path)


def jwks_document() -> dict:
    """Build the JWKS document exposed at `/.well-known/jwks.json`."""
    pub = _public_object()
    numbers = pub.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": current_kid(),
                "n": _b64url_uint(numbers.n),
                "e": _b64url_uint(numbers.e),
            }
        ]
    }
