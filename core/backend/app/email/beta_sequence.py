# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Beta onboarding email sequence (5 stages).

Stages:
  1. beta_welcome         — t=0
  2. beta_walkthrough     — t+24h
  3. beta_first_success   — t+3d
  4. beta_check_in        — t+7d
  5. beta_renewal_offer   — t+14d

`schedule_beta_sequence(license_jti, customer_email)` is idempotent:
the (license_jti, kind) pair is unique, so re-calling skips already-scheduled
rows. Sender uses the existing 019 email queue tick.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlmodel import Session, select

from app.db.models import EmailQueue
from app.db.session import get_engine

BETA_STAGES: list[tuple[str, timedelta]] = [
    ("beta_welcome", timedelta(seconds=0)),
    ("beta_walkthrough", timedelta(hours=24)),
    ("beta_first_success", timedelta(days=3)),
    ("beta_check_in", timedelta(days=7)),
    ("beta_renewal_offer", timedelta(days=14)),
]


def schedule_beta_sequence(
    *, license_jti: str, customer_email: str, now: datetime | None = None
) -> List[EmailQueue]:
    """Idempotently schedule all 5 beta-stage emails for a license."""
    base = now or datetime.now(timezone.utc)
    created: list[EmailQueue] = []
    with Session(get_engine()) as db:
        existing = {
            row.kind
            for row in db.scalars(
                select(EmailQueue).where(EmailQueue.license_jti == license_jti)
            ).all()
        }
        for kind, offset in BETA_STAGES:
            if kind in existing:
                continue
            row = EmailQueue(
                license_jti=license_jti,
                customer_email=customer_email,
                kind=kind,
                scheduled_at=base + offset,
            )
            db.add(row)
            created.append(row)
        db.commit()
        for row in created:
            db.refresh(row)
    return created


def beta_sequence_progress(*, license_jti: str) -> dict:
    """Return how many of the 5 stages are scheduled / sent for a license."""
    out = {
        "scheduled": 0,
        "sent": 0,
        "stages": {kind: {"scheduled_at": None, "sent_at": None} for kind, _ in BETA_STAGES},
    }
    kinds = {kind for kind, _ in BETA_STAGES}
    with Session(get_engine()) as db:
        rows = db.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == license_jti)
        ).all()
        for r in rows:
            if r.kind not in kinds:
                continue
            out["scheduled"] += 1
            stage = out["stages"][r.kind]
            stage["scheduled_at"] = r.scheduled_at.isoformat() if r.scheduled_at else None
            if r.sent_at is not None:
                out["sent"] += 1
                stage["sent_at"] = r.sent_at.isoformat()
    return out
