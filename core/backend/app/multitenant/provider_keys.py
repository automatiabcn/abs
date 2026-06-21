# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Per-owner provider key store + resolution (multi-tenant Phase 1).

CRUD over the `provider_keys` table plus `resolve_provider_key`, which returns
the most specific configured key for a request:

    project  →  user  →  org  →  global (settings/vault)

This is OPT-IN: nothing calls the resolver yet, so the existing cascade (which
reads global `settings.<provider>_api_key`) is unaffected. A later round wires
the resolver into request handling once the UI to manage keys ships.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import ProviderKey
from app.multitenant.crypto import decrypt_secret_value, encrypt_secret_value

logger = logging.getLogger(__name__)

OWNER_USER = "user"
OWNER_PROJECT = "project"
OWNER_ORG = "org"
_VALID_OWNER_TYPES = frozenset({OWNER_USER, OWNER_PROJECT, OWNER_ORG})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(value: str, field: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{field} is required")
    return v


def set_provider_key(
    *,
    tenant_slug: str,
    owner_type: str,
    owner_id: str,
    provider: str,
    value: str,
) -> ProviderKey:
    """Upsert an encrypted provider key for an owner. Returns the row."""
    tenant_slug = _normalize(tenant_slug, "tenant_slug")
    owner_type = _normalize(owner_type, "owner_type")
    owner_id = _normalize(owner_id, "owner_id")
    provider = _normalize(provider, "provider")
    if owner_type not in _VALID_OWNER_TYPES:
        raise ValueError(f"invalid owner_type: {owner_type}")
    if not (value or "").strip():
        raise ValueError("value is required")

    enc = encrypt_secret_value(value.strip())
    with Session(get_engine()) as db:
        row = db.exec(
            select(ProviderKey).where(
                ProviderKey.tenant_slug == tenant_slug,
                ProviderKey.owner_type == owner_type,
                ProviderKey.owner_id == owner_id,
                ProviderKey.provider == provider,
            )
        ).first()
        if row is None:
            row = ProviderKey(
                tenant_slug=tenant_slug,
                owner_type=owner_type,
                owner_id=owner_id,
                provider=provider,
                encrypted_value=enc,
                created_at=_now(),
            )
        else:
            row.encrypted_value = enc
            row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
    logger.info(
        "provider_key set tenant=%s owner=%s:%s provider=%s",
        tenant_slug,
        owner_type,
        owner_id,
        provider,
    )
    return row


def delete_provider_key(
    *, tenant_slug: str, owner_type: str, owner_id: str, provider: str
) -> bool:
    with Session(get_engine()) as db:
        row = db.exec(
            select(ProviderKey).where(
                ProviderKey.tenant_slug == tenant_slug,
                ProviderKey.owner_type == owner_type,
                ProviderKey.owner_id == owner_id,
                ProviderKey.provider == provider,
            )
        ).first()
        if row is None:
            return False
        db.delete(row)
        db.commit()
    return True


def get_owner_key(
    *, tenant_slug: str, owner_type: str, owner_id: str, provider: str
) -> Optional[str]:
    """Decrypted key for ONE specific owner row (not the resolution cascade).
    Used by the 'test this key' endpoint to ping with exactly that stored key."""
    with Session(get_engine()) as db:
        return _lookup(
            db,
            tenant_slug=_normalize(tenant_slug, "tenant_slug"),
            owner_type=_normalize(owner_type, "owner_type"),
            owner_id=_normalize(owner_id, "owner_id"),
            provider=_normalize(provider, "provider"),
        )


def mark_key_validated(
    *, tenant_slug: str, owner_type: str, owner_id: str, provider: str, ok: bool
) -> bool:
    """Record the outcome of a live key test (populates last_validated_ok/at —
    previously a dead column). Returns False if no such key row exists."""
    with Session(get_engine()) as db:
        row = db.exec(
            select(ProviderKey).where(
                ProviderKey.tenant_slug == _normalize(tenant_slug, "tenant_slug"),
                ProviderKey.owner_type == _normalize(owner_type, "owner_type"),
                ProviderKey.owner_id == _normalize(owner_id, "owner_id"),
                ProviderKey.provider == _normalize(provider, "provider"),
            )
        ).first()
        if row is None:
            return False
        row.last_validated_ok = ok
        row.last_validated_at = _now()
        db.add(row)
        db.commit()
    return True


def _lookup(
    db: Session, *, tenant_slug: str, owner_type: str, owner_id: str, provider: str
) -> Optional[str]:
    row = db.exec(
        select(ProviderKey).where(
            ProviderKey.tenant_slug == tenant_slug,
            ProviderKey.owner_type == owner_type,
            ProviderKey.owner_id == owner_id,
            ProviderKey.provider == provider,
        )
    ).first()
    if row is None:
        return None
    try:
        plain = decrypt_secret_value(row.encrypted_value)
    except Exception as exc:  # noqa: BLE001 — bad key → fall through to next tier
        logger.warning(
            "provider_key decrypt failed tenant=%s owner=%s:%s provider=%s: %s",
            tenant_slug,
            owner_type,
            owner_id,
            provider,
            exc,
        )
        return None
    return plain or None


def _global_key(provider: str) -> Optional[str]:
    """Legacy global key from settings/vault (the current single-tenant path)."""
    from app.config import settings
    from app.providers.cascade import SETTINGS_KEY_ATTR

    attr = SETTINGS_KEY_ATTR.get(provider)
    if not attr:
        return None
    val = (getattr(settings, attr, "") or "").strip()
    return val or None


def resolve_provider_key(
    provider: str,
    *,
    tenant_slug: str,
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
    include_global: bool = True,
) -> Optional[str]:
    """Most-specific configured key: project → user → org → global.

    Returns the decrypted key string, or None if nothing is configured at any
    tier. Tenant-scoped: only rows for `tenant_slug` are considered for the
    project/user/org tiers.
    """
    provider = (provider or "").strip()
    tenant_slug = (tenant_slug or "").strip()
    if not provider or not tenant_slug:
        return _global_key(provider) if include_global and provider else None

    with Session(get_engine()) as db:
        if project_slug:
            key = _lookup(
                db,
                tenant_slug=tenant_slug,
                owner_type=OWNER_PROJECT,
                owner_id=project_slug.strip(),
                provider=provider,
            )
            if key:
                return key
        if user_subject:
            key = _lookup(
                db,
                tenant_slug=tenant_slug,
                owner_type=OWNER_USER,
                owner_id=user_subject.strip(),
                provider=provider,
            )
            if key:
                return key
        key = _lookup(
            db,
            tenant_slug=tenant_slug,
            owner_type=OWNER_ORG,
            owner_id=tenant_slug,
            provider=provider,
        )
        if key:
            return key

    return _global_key(provider) if include_global else None


def tenant_configured_providers(
    *,
    tenant_slug: str,
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> set[str]:
    """Providers that have a per-owner (project/user/org) key for this tenant.

    Used so the cascade can activate a provider that the operator did NOT
    configure globally but a user/project supplied their own key for (BYOK).
    DB-only (no global fallback) — global providers are already handled by
    `is_configured`.
    """
    from app.providers.cascade import SETTINGS_KEY_ATTR

    tenant_slug = (tenant_slug or "").strip()
    if not tenant_slug:
        return set()
    out: set[str] = set()
    for provider in SETTINGS_KEY_ATTR:
        if resolve_provider_key(
            provider,
            tenant_slug=tenant_slug,
            project_slug=project_slug,
            user_subject=user_subject,
            include_global=False,
        ):
            out.add(provider)
    return out


def list_provider_keys(*, tenant_slug: str) -> list[dict]:
    """Metadata for a tenant's keys — NEVER returns plaintext."""
    tenant_slug = (tenant_slug or "").strip()
    with Session(get_engine()) as db:
        rows = db.exec(
            select(ProviderKey).where(ProviderKey.tenant_slug == tenant_slug)
        ).all()
    return [
        {
            "owner_type": r.owner_type,
            "owner_id": r.owner_id,
            "provider": r.provider,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "last_validated_ok": r.last_validated_ok,
        }
        for r in rows
    ]
