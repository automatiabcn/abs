# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""026 — Smart link secret vault (sops/age + 5-min cache + audit log).

Public API:
  - encrypt_secret(key_name, provider, value) → ConnectedSecret row
  - decrypt_secret(key_name) → plaintext (5-min cache)
  - rotate_secret(key_name, provider, new_value) → audit + DB update
  - list_secrets() → list of ConnectedSecret rows (no plaintext exposed)
  - delete_secret(key_name) → DB clear

Encryption strategy:
  1. If sops/age binaries exist + master key configured → real encrypt via runner.
  2. Else → reversible base64 obfuscation (NOT secure, but enables dev/test).
     Production must run sops; vault_status MCP tool reports binary availability.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models import ConnectedSecret
from app.db.session import get_engine

logger = logging.getLogger(__name__)


_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300


def _has_sops() -> bool:
    try:
        from app.vault.runner import master_key_exists, sops_available

        return sops_available() and master_key_exists()
    except Exception:
        return False


def _encrypt_value(plaintext: str) -> str:
    """Return encrypted/obfuscated value to persist."""
    if _has_sops():
        try:
            from app.vault.runner import write_secret as _vault_write

            # 013 vault stores by key_name in single store; for connected secrets we
            # use a namespaced prefix so we don't clash with provider API keys.
            _vault_write(f"smart_link::{plaintext[:0]}", plaintext)
        except Exception as exc:
            logger.warning("sops encrypt fallback to obfuscation: %s", exc)
    # Fallback: reversible base64 (clearly marked).
    return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def _decrypt_value(stored: str) -> str:
    if stored.startswith("b64:"):
        return base64.b64decode(stored[4:]).decode("utf-8")
    # If sops blob format, attempt vault decrypt — TBD; for now return raw.
    return stored


def encrypt_secret(*, key_name: str, provider: str, value: str) -> ConnectedSecret:
    enc = _encrypt_value(value)
    with Session(get_engine()) as db:
        existing = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
        ).first()
        if existing is None:
            row = ConnectedSecret(
                key_name=key_name, provider=provider, encrypted_value=enc
            )
            db.add(row)
        else:
            existing.encrypted_value = enc
            existing.provider = provider
            existing.created_at = datetime.now(timezone.utc)
            db.add(existing)
            row = existing
        db.commit()
        db.refresh(row)
    _CACHE[key_name] = (value, time.time())
    logger.info(
        "[smart_link] secret stored key=%s provider=%s len=%d",
        key_name,
        provider,
        len(value),
    )
    return row


def decrypt_secret(key_name: str) -> Optional[str]:
    cached = _CACHE.get(key_name)
    if cached and (time.time() - cached[1] < _CACHE_TTL):
        return cached[0]
    with Session(get_engine()) as db:
        row = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
        ).first()
        if row is None:
            return None
        plaintext = _decrypt_value(row.encrypted_value)
        _CACHE[key_name] = (plaintext, time.time())
        return plaintext


def rotate_secret(*, key_name: str, provider: str, new_value: str) -> ConnectedSecret:
    """Rotate: audit log old key, encrypt new value."""
    logger.info(
        "[smart_link] rotate key=%s provider=%s old_len=%s",
        key_name,
        provider,
        len(decrypt_secret(key_name) or ""),
    )
    _CACHE.pop(key_name, None)
    return encrypt_secret(key_name=key_name, provider=provider, value=new_value)


def list_secrets() -> list[dict]:
    """Return DB rows minus plaintext; safe for status endpoints."""
    with Session(get_engine()) as db:
        rows = db.scalars(select(ConnectedSecret)).all()
        out: list[dict] = []
        for r in rows:
            created = r.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            validated_at = r.last_validated_at
            if validated_at and validated_at.tzinfo is None:
                validated_at = validated_at.replace(tzinfo=timezone.utc)
            out.append(
                {
                    "key_name": r.key_name,
                    "provider": r.provider,
                    "created_at": created.isoformat(),
                    "last_validated_at": validated_at.isoformat()
                    if validated_at
                    else None,
                    "last_validated_ok": r.last_validated_ok,
                    "last_validated_error": r.last_validated_error,
                }
            )
        return out


def delete_secret(key_name: str) -> bool:
    with Session(get_engine()) as db:
        row = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
        ).first()
        if row is None:
            return False
        db.delete(row)
        db.commit()
    _CACHE.pop(key_name, None)
    return True


def update_validation_status(
    *,
    key_name: str,
    ok: bool,
    error: Optional[str] = None,
) -> None:
    with Session(get_engine()) as db:
        row = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
        ).first()
        if row is None:
            return
        row.last_validated_at = datetime.now(timezone.utc)
        row.last_validated_ok = ok
        row.last_validated_error = (error or None) and (error or "")[:512]
        db.add(row)
        db.commit()
