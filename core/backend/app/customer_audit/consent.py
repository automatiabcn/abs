# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""029 Modul D — GDPR Article 7 consent tracking helpers.

Consent types tracked:
  - tos                    — Terms of Service
  - privacy                — Privacy Policy
  - dpa                    — Data Processing Agreement (B2B/team tier)
  - marketing_email        — optional, default off
  - product_updates_email  — optional, default off

Operations:
  - grant_consent(jti, type, version, source) → upsert with granted_at=now
  - withdraw_consent(jti, type)               → mark withdrawn_at=now
  - has_consent(jti, type)                    → bool (granted, not withdrawn)
  - list_consents(jti)                        → all rows for a license
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app.db.models import Consent
from app.db.session import get_engine

CONSENT_TYPES = {
    "tos",
    "privacy",
    "dpa",
    "marketing_email",
    "product_updates_email",
}


def grant_consent(
    *,
    license_jti: str,
    consent_type: str,
    version: str = "1.0",
    source: str = "setup_wizard",
) -> Consent:
    """Idempotent: same (jti, type) updates row instead of duplicating."""
    if consent_type not in CONSENT_TYPES:
        raise ValueError(f"unknown consent_type: {consent_type}")
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        existing = db.scalars(
            select(Consent)
            .where(Consent.license_jti == license_jti)
            .where(Consent.consent_type == consent_type)
        ).first()
        if existing is None:
            row = Consent(
                license_jti=license_jti,
                consent_type=consent_type,
                version=version,
                granted_at=now,
                withdrawn_at=None,
                source=source,
            )
            db.add(row)
        else:
            existing.version = version
            existing.granted_at = now
            existing.withdrawn_at = None
            existing.source = source
            db.add(existing)
            row = existing
        db.commit()
        db.refresh(row)
    return row


def withdraw_consent(*, license_jti: str, consent_type: str) -> Optional[Consent]:
    if consent_type not in CONSENT_TYPES:
        raise ValueError(f"unknown consent_type: {consent_type}")
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = db.scalars(
            select(Consent)
            .where(Consent.license_jti == license_jti)
            .where(Consent.consent_type == consent_type)
        ).first()
        if row is None:
            return None
        row.withdrawn_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def has_consent(*, license_jti: str, consent_type: str) -> bool:
    with Session(get_engine()) as db:
        row = db.scalars(
            select(Consent)
            .where(Consent.license_jti == license_jti)
            .where(Consent.consent_type == consent_type)
        ).first()
    return bool(row and row.granted_at and not row.withdrawn_at)


def list_consents(*, license_jti: str) -> List[dict]:
    with Session(get_engine()) as db:
        rows = list(
            db.scalars(
                select(Consent).where(Consent.license_jti == license_jti)
            ).all()
        )
    return [
        {
            "consent_type": r.consent_type,
            "version": r.version,
            "granted_at": r.granted_at.isoformat() if r.granted_at else None,
            "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
            "source": r.source,
            "active": bool(r.granted_at and not r.withdrawn_at),
        }
        for r in rows
    ]
