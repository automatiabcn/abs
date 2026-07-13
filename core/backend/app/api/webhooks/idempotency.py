# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Webhook idempotency guard: process each `event.id` exactly once.

Stripe re-sends the same `event.id` after a network failure or a replay, so a
handler must claim the event before doing any work:
- claim_event INSERTs the row → do the work, then mark_processed.
- A unique-constraint violation means someone already claimed it, so
  DuplicateEventError is raised and the handler answers 200 + duplicate=True.

The claim is the DB unique index, not an in-process check, so it also holds
across concurrent workers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import WebhookEvent


class DuplicateEventError(Exception):
    """This event_id was already claimed. Handlers answer 200 + duplicate."""

    def __init__(self, event_id: str, license_jti: Optional[str] = None):
        self.event_id = event_id
        self.license_jti = license_jti
        super().__init__(f"duplicate event_id={event_id}")


def claim_event(db: Session, event_id: str, event_type: str) -> WebhookEvent:
    """Claim an event as "in progress".

    Raises DuplicateEventError if the row already exists. Returns the new
    WebhookEvent row; the caller sets `processed_at` and `license_jti` once the
    work is done.
    """
    row = WebhookEvent(event_id=event_id, event_type=event_type)
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = db.scalars(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        ).first()
        raise DuplicateEventError(
            event_id=event_id,
            license_jti=existing.license_jti if existing else None,
        )


def mark_processed(
    db: Session,
    row: WebhookEvent,
    license_jti: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Mark a claimed event as finished. `error` is truncated to 512 chars."""
    row.processed_at = datetime.now(timezone.utc)
    row.license_jti = license_jti
    row.error = error[:512] if error else None
    db.add(row)
    db.commit()
