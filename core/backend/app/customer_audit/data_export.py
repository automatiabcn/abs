# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GDPR data export (Article 15 right of access).

Builds a ZIP containing all data tied to a license:
  - license.json
  - audit_log.jsonl
  - webhook_events.jsonl
  - connected_secrets.json (provider names only, NO plaintext)
  - email_queue.jsonl
  - consents.jsonl
  - README.txt

ZIP is encrypted with a Fernet key derived from sha256(jti + customer_email).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple

from cryptography.fernet import Fernet
from sqlmodel import Session, select

from app.config import settings
from app.db.models import (
    Consent,
    CustomerAuditEntry,
    DataExportJob,
    EmailQueue,
    License,
    WebhookEvent,
)
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def _derive_fernet_key(*, license_jti: str, customer_email: str) -> bytes:
    """Deterministic Fernet key from (jti + email)."""
    raw = (license_jti + ":" + customer_email).encode("utf-8")
    digest = hashlib.sha256(raw).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)


def _new_job_id() -> str:
    return "dxj_" + secrets.token_urlsafe(20)


def _output_dir() -> Path:
    p = Path(settings.data_dir) / "data_exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_zip(license_jti: str, customer_email: str) -> bytes:
    """Build the in-memory plaintext ZIP for this license."""
    buffer = io.BytesIO()
    with Session(get_engine()) as db:
        license_row = db.scalars(
            select(License).where(License.jti == license_jti)
        ).first()
        license_data = (
            {
                "jti": license_row.jti,
                "customer_email": license_row.customer_email,
                "tier": license_row.tier,
                "seat_count": license_row.seat_count,
                "issued_at": license_row.issued_at.isoformat(),
                "expires_at": license_row.expires_at.isoformat(),
                "preferred_lang": license_row.preferred_lang,
            }
            if license_row
            else {}
        )

        audit_rows = db.scalars(
            select(CustomerAuditEntry)
            .where(CustomerAuditEntry.license_jti == license_jti)
            .order_by(CustomerAuditEntry.ts)  # type: ignore[union-attr]
        ).all()
        webhook_rows = db.scalars(
            select(WebhookEvent).where(
                WebhookEvent.license_jti == license_jti
            )
        ).all()
        email_rows = db.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == license_jti)
        ).all()
        consent_rows = db.scalars(
            select(Consent).where(Consent.license_jti == license_jti)
        ).all()

    audit_entries = [
        {
            "ts": r.ts.isoformat() if r.ts else None,
            "action": r.action,
            "resource": r.resource,
            "detail": r.detail,
        }
        for r in audit_rows
    ]
    webhook_entries = [
        {
            "event_id": r.event_id,
            "event_type": r.event_type,
            "received_at": r.received_at.isoformat() if r.received_at else None,
            "license_jti": r.license_jti,
        }
        for r in webhook_rows
    ]
    email_entries = [
        {
            "kind": r.kind,
            "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "attempts": r.attempts,
        }
        for r in email_rows
    ]
    consent_entries = [
        {
            "consent_type": r.consent_type,
            "version": r.version,
            "granted_at": r.granted_at.isoformat() if r.granted_at else None,
            "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
            "source": r.source,
        }
        for r in consent_rows
    ]

    readme = (
        "Automatia ABS — GDPR Data Export\n"
        "=================================\n\n"
        f"License JTI: {license_jti}\n"
        f"Customer Email: {customer_email}\n"
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        "Files in this archive:\n"
        "  license.json          — Your license metadata\n"
        "  audit_log.jsonl       — Actions taken by your account\n"
        "  webhook_events.jsonl  — Stripe events tied to your license\n"
        "  email_queue.jsonl     — Onboarding emails queued / sent\n"
        "  consents.jsonl        — Consent records\n"
        "  connected_secrets.json — Smart-link provider names (no secrets)\n\n"
        "This archive satisfies GDPR Article 15 (right of access).\n"
        "Contact: privacy@automatiabcn.com\n"
    )

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("license.json", json.dumps(license_data, indent=2))
        zf.writestr(
            "audit_log.jsonl",
            "\n".join(json.dumps(a) for a in audit_entries),
        )
        zf.writestr(
            "webhook_events.jsonl",
            "\n".join(json.dumps(a) for a in webhook_entries),
        )
        zf.writestr(
            "email_queue.jsonl",
            "\n".join(json.dumps(a) for a in email_entries),
        )
        zf.writestr(
            "consents.jsonl",
            "\n".join(json.dumps(a) for a in consent_entries),
        )
        zf.writestr("connected_secrets.json", json.dumps([], indent=2))

    return buffer.getvalue()


def create_export_job(*, license_jti: str, customer_email: str) -> DataExportJob:
    """Persist a job row in `queued` state; caller invokes `run_export_job` to fill."""
    job_id = _new_job_id()
    with Session(get_engine()) as db:
        row = DataExportJob(
            job_id=job_id,
            license_jti=license_jti,
            customer_email=customer_email,
            status="queued",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def run_export_job(job_id: str) -> dict:
    """Build ZIP, encrypt, write to disk, mark job done."""
    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job_id)
        ).first()
        if row is None:
            return {"ok": False, "error": "job_not_found"}
        license_jti = row.license_jti
        customer_email = row.customer_email

    plaintext = _build_zip(license_jti, customer_email)
    fernet_key = _derive_fernet_key(
        license_jti=license_jti, customer_email=customer_email
    )
    ciphertext = Fernet(fernet_key).encrypt(plaintext)

    out_path = _output_dir() / f"{job_id}.zip.enc"
    out_path.write_bytes(ciphertext)

    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job_id)
        ).first()
        if row is not None:
            row.status = "done"
            row.completed_at = datetime.now(timezone.utc)
            row.output_path = str(out_path)
            db.add(row)
            db.commit()

    return {"ok": True, "job_id": job_id, "path": str(out_path), "size": len(ciphertext)}


def decrypt_export(
    *, license_jti: str, customer_email: str, ciphertext: bytes
) -> bytes:
    """Helper for tests / CLI: decrypt an exported archive."""
    key = _derive_fernet_key(license_jti=license_jti, customer_email=customer_email)
    return Fernet(key).decrypt(ciphertext)
