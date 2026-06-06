# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""At-rest encryption for per-owner provider keys (multi-tenant Phase 1).

Stored values are versioned so the format is self-describing and migratable:
  * ``fernet:<token>`` — AES128-CBC + HMAC via cryptography.Fernet, key derived
    from ``settings.provider_key_encryption_key`` (sha256 → urlsafe-b64).
  * ``b64:<blob>``     — reversible base64 obfuscation (DEV ONLY, NOT secure),
    used when no encryption key is configured so tests/dev keep working.

Production MUST set ``ABS_PROVIDER_KEY_ENCRYPTION_KEY``; a one-time warning is
logged when the insecure fallback is used.
"""

from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "fernet:"
_B64_PREFIX = "b64:"

_warned_insecure = False


def _derive_fernet_key(secret: str) -> bytes:
    """sha256(secret) → urlsafe-b64 32-byte Fernet key (accepts any string)."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _encryption_secret() -> str:
    from app.config import settings

    return (getattr(settings, "provider_key_encryption_key", "") or "").strip()


def encrypt_secret_value(plaintext: str) -> str:
    """Encrypt a provider key for DB storage. Returns a versioned string."""
    secret = _encryption_secret()
    if secret:
        try:
            from cryptography.fernet import Fernet

            token = Fernet(_derive_fernet_key(secret)).encrypt(
                plaintext.encode("utf-8")
            )
            return _FERNET_PREFIX + token.decode("ascii")
        except Exception as exc:  # noqa: BLE001 — never lose the value
            logger.warning("provider key fernet encrypt failed, using b64: %s", exc)
    global _warned_insecure
    if not _warned_insecure:
        logger.warning(
            "ABS_PROVIDER_KEY_ENCRYPTION_KEY unset — provider keys stored with "
            "INSECURE base64 obfuscation. Set it in production."
        )
        _warned_insecure = True
    return _B64_PREFIX + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret_value(stored: str) -> str:
    """Inverse of :func:`encrypt_secret_value`. Tolerant of legacy raw values."""
    if not stored:
        return ""
    if stored.startswith(_FERNET_PREFIX):
        from cryptography.fernet import Fernet

        secret = _encryption_secret()
        if not secret:
            raise ValueError(
                "provider key is fernet-encrypted but no encryption key configured"
            )
        token = stored[len(_FERNET_PREFIX) :].encode("ascii")
        return Fernet(_derive_fernet_key(secret)).decrypt(token).decode("utf-8")
    if stored.startswith(_B64_PREFIX):
        return base64.b64decode(stored[len(_B64_PREFIX) :]).decode("utf-8")
    # Legacy / plaintext fallback (should not happen for new rows).
    return stored
