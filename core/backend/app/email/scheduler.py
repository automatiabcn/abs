# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Onboarding email scheduler.

Five-mail series: welcome (1h), walkthrough (24h), expiry_warning (10d),
recovery (21d), plus first_success, which is not on a clock — it fires the
moment the customer's first MCP tool call lands.

`tick()` is meant to run on a short cron and only picks up rows that are due,
unsent and not unsubscribed, so a missed run delays mail but never loses it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlmodel import Session, select

from app.config import settings
from app.db.models import EmailQueue, License
from app.db.session import get_session_sync

logger = logging.getLogger(__name__)


# When each mail is due, relative to license activation.
_OFFSETS = {
    "welcome": timedelta(hours=1),
    "walkthrough": timedelta(hours=24),
    "expiry_warning": timedelta(days=10),
    "recovery": timedelta(days=21),
}


def _make_unsubscribe_token(license_jti: str) -> str:
    """Unsubscribe token — HS256, valid for a year."""
    import jwt

    payload = {
        "license_jti": license_jti,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp()),
    }
    return jwt.encode(payload, settings.unsubscribe_jwt_secret, algorithm="HS256")


def _unsubscribe_url(token: str) -> str:
    base = settings.domain or "abs.local"
    if not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/v1/email/unsubscribe?token={token}"


def schedule_onboarding(
    *, license_jti: str, email: str, db: Optional[Session] = None
) -> int:
    """Queue the four timed onboarding mails for a new license.

    first_success is queued separately (`schedule_first_success`). Returns the
    number of rows added.
    """
    now = datetime.now(timezone.utc)
    rows = []
    for kind, offset in _OFFSETS.items():
        rows.append(
            EmailQueue(
                license_jti=license_jti,
                customer_email=email,
                kind=kind,
                scheduled_at=now + offset,
            )
        )

    own_session = db is None
    if own_session:
        ctx = get_session_sync()
        db = ctx.__enter__()
    try:
        for r in rows:
            db.add(r)
        db.commit()
        return len(rows)
    finally:
        if own_session:
            ctx.__exit__(None, None, None)  # type: ignore[union-attr]


def schedule_first_success(
    *, license_jti: str, email: str, db: Optional[Session] = None
) -> bool:
    """Queue the first_success mail, due immediately. Idempotent per license."""
    own_session = db is None
    if own_session:
        ctx = get_session_sync()
        db = ctx.__enter__()
    try:
        # One first_success per license — a second tool call must not re-send it.
        existing = db.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == license_jti)
            .where(EmailQueue.kind == "first_success")
        ).first()
        if existing is not None:
            return False
        db.add(
            EmailQueue(
                license_jti=license_jti,
                customer_email=email,
                kind="first_success",
                scheduled_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return True
    finally:
        if own_session:
            ctx.__exit__(None, None, None)  # type: ignore[union-attr]


def _render_for(row: EmailQueue, db: Session) -> Tuple[str, str]:
    """Render the template for this row, in the license holder's language."""
    from app.email.sender import _render

    token = _make_unsubscribe_token(row.license_jti)
    unsubscribe_url = _unsubscribe_url(token)

    ctx = {
        "customer_email": row.customer_email,
        "license_jti": row.license_jti,
        "unsubscribe_url": unsubscribe_url,
        # Q12-R84 — pricing pulled from settings; templates render "" when 0.0.
        "maintenance_price_yearly": (
            f"{settings.abs_maintenance_price_yearly:.0f}"
            if settings.abs_maintenance_price_yearly > 0
            else ""
        ),
        "annual_offer_strike": (
            f"{settings.abs_annual_offer_strike:.0f}"
            if settings.abs_annual_offer_strike > 0
            else ""
        ),
        "annual_offer_price": (
            f"{settings.abs_annual_offer_price:.0f}"
            if settings.abs_annual_offer_price > 0
            else ""
        ),
    }

    if row.kind == "expiry_warning":
        lic = db.scalars(select(License).where(License.jti == row.license_jti)).first()
        if lic is not None:
            expires_at = lic.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_left = max(0, (expires_at - now).days)
            ctx["days_left"] = days_left
            ctx["expires_at"] = expires_at.strftime("%Y-%m-%d")
        else:
            ctx["days_left"] = 0
            ctx["expires_at"] = "?"
        ctx["portal_url"] = f"{settings.domain or 'abs.automatiabcn.com'}/manage"

    elif row.kind == "recovery":
        lic = db.scalars(select(License).where(License.jti == row.license_jti)).first()
        if lic is not None:
            expires_at = lic.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            ctx["expires_at"] = expires_at.strftime("%Y-%m-%d")
        else:
            ctx["expires_at"] = "?"

    elif row.kind == "first_success":
        ctx["first_tool_name"] = "system_status"

    # Preferred_lang from License row (default 'en')
    lic = db.scalars(select(License).where(License.jti == row.license_jti)).first()
    lang = lic.preferred_lang if (lic and lic.preferred_lang) else "en"
    return _render(f"{row.kind}.html", lang=lang, **ctx)


def tick(now: Optional[datetime] = None) -> Tuple[int, int]:
    """Send every mail that is now due. Returns (sent, failed)."""
    from app.email.sender import _send_html

    if now is None:
        now = datetime.now(timezone.utc)

    sent = 0
    failed = 0

    with get_session_sync() as db:
        rows = db.scalars(
            select(EmailQueue)
            .where(EmailQueue.sent_at.is_(None))  # type: ignore[union-attr]
            .where(EmailQueue.scheduled_at <= now)
            .where(EmailQueue.unsubscribed == False)  # noqa: E712
            .where(EmailQueue.attempts < 3)
        ).all()

        for row in rows:
            try:
                subject, html = _render_for(row, db)
                _send_html(
                    to=row.customer_email,
                    subject=subject,
                    html=html,
                    kind=row.kind,
                )
                row.sent_at = datetime.now(timezone.utc)
                row.attempts += 1
                row.error = None
                db.add(row)
                sent += 1
            except Exception as exc:
                row.attempts += 1
                row.error = str(exc)[:512]
                # Exponential backoff: 5min × 2^attempt
                backoff = timedelta(minutes=5 * (2**row.attempts))
                row.scheduled_at = datetime.now(timezone.utc) + backoff
                db.add(row)
                failed += 1
                logger.exception(
                    "[email_scheduler] kind=%s jti=%s err=%s",
                    row.kind,
                    row.license_jti,
                    exc,
                )
        db.commit()

    return sent, failed


def unsubscribe(token: str) -> Tuple[bool, Optional[str]]:
    """JWT verify → email_queue.unsubscribed=True.

    Returns: (ok, license_jti or error_msg).
    """
    import jwt

    try:
        payload = jwt.decode(
            token, settings.unsubscribe_jwt_secret, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        return False, "Token expired"
    except jwt.InvalidTokenError as exc:
        logger.warning("email unsubscribe invalid token: %s", type(exc).__name__)
        return False, "Invalid token"

    license_jti = payload.get("license_jti")
    if not license_jti:
        return False, "Token does not contain license_jti"

    with get_session_sync() as db:
        rows = db.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == license_jti)
        ).all()
        for r in rows:
            r.unsubscribed = True
            db.add(r)
        db.commit()

    return True, license_jti
