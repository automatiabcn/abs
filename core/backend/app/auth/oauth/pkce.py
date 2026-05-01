"""T-003 — PKCE (RFC 7636) S256 verification.

OAuth 2.1 mandates `code_challenge_method = S256`; `plain` is rejected.
"""

from __future__ import annotations

import base64
import hashlib

__all__ = ["verify_s256"]


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def verify_s256(code_verifier: str, expected_challenge: str) -> bool:
    """Return True iff `BASE64URL(SHA256(code_verifier))` matches challenge.

    `code_verifier` length must be 43..128 chars per RFC 7636 §4.1.
    """
    if not code_verifier or not (43 <= len(code_verifier) <= 128):
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return _b64url_no_pad(digest) == expected_challenge
