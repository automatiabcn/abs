# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Consent Ledger service — set/get consent + the channel gate. Tenant-scoped.

``check_channel`` is the concrete compliance defence: an outbound action on a
channel is allowed ONLY when the contact's consent record permits it. Absence of
a record = not allowed (fail-closed). Used by outbound/approval flows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.db.growth_models import ConsentRecord
from app.db.session import get_engine

# channel -> consent column
_CHANNEL_FIELD = {
    "email": "email_consent",
    "phone": "phone_consent",
    "call": "phone_consent",
    "sms": "sms_consent",
    "whatsapp": "whatsapp_consent",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(r: ConsentRecord) -> dict:
    return {
        "contact_email": r.contact_email,
        "email_consent": r.email_consent,
        "phone_consent": r.phone_consent,
        "sms_consent": r.sms_consent,
        "whatsapp_consent": r.whatsapp_consent,
        "do_not_call": r.do_not_call,
        "opt_in_source": r.opt_in_source,
        "legal_basis": r.legal_basis,
        "opt_out_at": r.opt_out_at.isoformat() if r.opt_out_at else None,
        "allowed_channels": [
            ch
            for ch, f in (
                ("email", "email_consent"),
                ("phone", "phone_consent"),
                ("sms", "sms_consent"),
                ("whatsapp", "whatsapp_consent"),
            )
            if getattr(r, f) and not r.opt_out_at
        ],
    }


def set_consent(*, tenant_slug: str, contact_email: str, **fields: Any) -> dict:
    """Upsert a contact's consent record (idempotent on contact_email)."""
    tenant_slug = (tenant_slug or "default").strip()
    contact_email = (contact_email or "").strip().lower()
    with Session(get_engine()) as db:
        row = db.exec(
            select(ConsentRecord).where(
                ConsentRecord.tenant_slug == tenant_slug,
                ConsentRecord.contact_email == contact_email,
            )
        ).first()
        if row is None:
            row = ConsentRecord(tenant_slug=tenant_slug, contact_email=contact_email)
        for k, v in fields.items():
            if hasattr(ConsentRecord, k) and k not in (
                "id",
                "tenant_slug",
                "contact_email",
            ):
                setattr(row, k, v)
        if (
            any(
                fields.get(c)
                for c in (
                    "email_consent",
                    "phone_consent",
                    "sms_consent",
                    "whatsapp_consent",
                )
            )
            and row.opt_in_at is None
        ):
            row.opt_in_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def get_consent(*, tenant_slug: str, contact_email: str) -> Optional[dict]:
    tenant_slug = (tenant_slug or "default").strip()
    contact_email = (contact_email or "").strip().lower()
    with Session(get_engine()) as db:
        row = db.exec(
            select(ConsentRecord).where(
                ConsentRecord.tenant_slug == tenant_slug,
                ConsentRecord.contact_email == contact_email,
            )
        ).first()
        return _to_dict(row) if row else None


def check_channel(
    *, tenant_slug: str, contact_email: str, channel: str
) -> Dict[str, Any]:
    """The gate: may we contact this person on this channel? Fail-closed."""
    field = _CHANNEL_FIELD.get((channel or "").strip().lower())
    if field is None:
        return {"allowed": False, "reason": f"unknown_channel:{channel}"}
    rec = get_consent(tenant_slug=tenant_slug, contact_email=contact_email)
    if rec is None:
        return {"allowed": False, "reason": "no_consent_on_file", "status": "unknown"}
    if rec.get("opt_out_at"):
        return {"allowed": False, "reason": "opted_out", "status": "opt-out"}
    if channel in ("phone", "call") and rec.get("do_not_call"):
        return {"allowed": False, "reason": "do_not_call", "status": "dnc"}
    consent_key = {
        "email": "email_consent",
        "phone": "phone_consent",
        "call": "phone_consent",
        "sms": "sms_consent",
        "whatsapp": "whatsapp_consent",
    }[channel]
    if rec.get(consent_key):
        return {
            "allowed": True,
            "reason": "consent_granted",
            "status": "opt-in",
            "legal_basis": rec.get("legal_basis", ""),
        }
    return {"allowed": False, "reason": "channel_not_consented", "status": "unknown"}
