# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""017 — Webhook idempotency guard: event_id bazlı tek-sefer-işleme.

Stripe ağ hatasında veya replay'de aynı `event.id`'yi tekrar gönderebilir.
Handler önce `claim_event` çağırır:
- INSERT başarılı → işle, sonunda `mark_processed`.
- IntegrityError → DuplicateEventError raise; handler 200 + duplicate=True döner.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import WebhookEvent


class DuplicateEventError(Exception):
    """Aynı event_id daha önce işlendi — handler 200 + duplicate döner."""

    def __init__(self, event_id: str, license_jti: Optional[str] = None):
        self.event_id = event_id
        self.license_jti = license_jti
        super().__init__(f"duplicate event_id={event_id}")


def claim_event(db: Session, event_id: str, event_type: str) -> WebhookEvent:
    """Event'i 'işleniyor' olarak claim et.

    INSERT dener; duplicate ise IntegrityError yakalar ve DuplicateEventError raise eder.
    Returns: yeni WebhookEvent row (caller `processed_at` ve `license_jti`'yi
    sonra set eder).
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
    """Claim edilmiş event'i tamamlandı olarak işaretle."""
    row.processed_at = datetime.now(timezone.utc)
    row.license_jti = license_jti
    row.error = error[:512] if error else None
    db.add(row)
    db.commit()
