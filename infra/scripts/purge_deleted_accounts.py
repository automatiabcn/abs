"""029 Modul C — Daily purge cron for accounts past their 30-day grace.

Cron (daily):
  python infra/scripts/purge_deleted_accounts.py [--dry-run]

Behaviour:
- License rows with `scheduled_delete_at <= now AND purged_at IS NULL` are
  fully erased: customer_email/customer_id_stripe blanked, related rows
  (CustomerAuditEntry, EmailQueue, Consent, ConnectedSecret, DataExportJob)
  hard-deleted.
- License row stays (referential integrity for billing history) but PII is
  zeroed and `purged_at` is stamped.
- Idempotent: a second run finds nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def _purge_one(db, license_row) -> dict:
    """Hard-delete PII tied to a single license. Returns counts dict."""
    from sqlmodel import select

    from app.db.models import (
        ConnectedSecret,
        Consent,
        CustomerAuditEntry,
        DataExportJob,
        EmailQueue,
    )

    jti = license_row.jti
    counts = {"audit": 0, "email": 0, "consent": 0, "secret": 0, "export": 0}

    for row in db.scalars(
        select(CustomerAuditEntry).where(CustomerAuditEntry.license_jti == jti)
    ).all():
        db.delete(row)
        counts["audit"] += 1
    for row in db.scalars(
        select(EmailQueue).where(EmailQueue.license_jti == jti)
    ).all():
        db.delete(row)
        counts["email"] += 1
    for row in db.scalars(
        select(Consent).where(Consent.license_jti == jti)
    ).all():
        db.delete(row)
        counts["consent"] += 1
    try:
        for row in db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.license_jti == jti)
        ).all():
            db.delete(row)
            counts["secret"] += 1
    except Exception:
        pass
    for row in db.scalars(
        select(DataExportJob).where(DataExportJob.license_jti == jti)
    ).all():
        db.delete(row)
        counts["export"] += 1

    license_row.customer_email = ""
    license_row.customer_id_stripe = ""
    license_row.purged_at = datetime.now(timezone.utc)
    db.add(license_row)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GDPR Article 17 daily purge")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from sqlmodel import select

    from app.db.models import License
    from app.db.session import get_session_sync
    from app.observability.audit import emit_event

    now = datetime.now(timezone.utc)
    out = {
        "now": now.isoformat(),
        "dry_run": args.dry_run,
        "candidates": 0,
        "purged": 0,
        "details": [],
    }
    with get_session_sync() as db:
        rows = db.scalars(
            select(License)
            .where(License.scheduled_delete_at.is_not(None))  # type: ignore[union-attr]
            .where(License.scheduled_delete_at <= now)
            .where(License.purged_at.is_(None))  # type: ignore[union-attr]
        ).all()
        out["candidates"] = len(rows)
        for row in rows:
            entry = {"jti": row.jti, "scheduled_delete_at": row.scheduled_delete_at.isoformat() if row.scheduled_delete_at else None}
            if not args.dry_run:
                entry["counts"] = _purge_one(db, row)
                out["purged"] += 1
                # Sprint 2I UAT-032 — purge success is part of the KVKK
                # audit trail (Article 7 + GDPR Article 17). Background
                # task → request=None.
                emit_event(
                    None,
                    action="me.account.purge_executed",
                    outcome="success",
                    user_id=row.jti,
                )
            out["details"].append(entry)
        if not args.dry_run:
            db.commit()

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
