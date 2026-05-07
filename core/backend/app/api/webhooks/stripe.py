# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stripe webhook endpoint.

`checkout.session.completed` event'ini yakalar: lisans üretir, DB'ye kaydeder,
müşteriye email gönderir. Diğer event'ler 200 "ignored" döner.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.api.webhooks.idempotency import (
    DuplicateEventError,
    claim_event,
    mark_processed,
)
from app.config import settings
from app.db.models import License
from app.db.session import get_session
from app.email.sender import send_license_email
from app.i18n import t
from app.licensing import generate_license, verify_license
from app.observability.audit import emit_event  # Q12-L24 sweep 2

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# module-level: boot'ta tek sefer (per-request mutation race'ini önler)
stripe.api_key = settings.stripe_secret_key


def _parse_seat_count(raw) -> int:
    """Stripe metadata'dan gelen seat_count'u güvenli şekilde parse et."""
    if raw is None:
        return 1
    s = str(raw).strip()
    if s.isdigit() and int(s) >= 1:
        return int(s)
    return 1


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_session),
) -> dict:
    """Stripe webhook işleyicisi — imza doğrula, event'e göre aksiyon al."""
    payload = await request.body()
    lang = getattr(request.state, "lang", "en")
    sig_header = request.headers.get("stripe-signature")
    if sig_header is None:
        emit_event(
            request,
            action="webhooks.stripe.signature",
            outcome="denied",
            reason="signature_missing",
            status_code=400,
            provider="stripe",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.signature_missing", lang),
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError as exc:
        # Q12-L24 sweep 2 — exc carries Stripe SDK internals (`Could
        # not deserialize key data...`). Keep response generic via i18n
        # and route taxonomy + error_class to the audit channel.
        emit_event(
            request,
            action="webhooks.stripe.payload",
            outcome="denied",
            reason="payload_invalid",
            status_code=400,
            provider="stripe",
            error_class=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.payload_invalid", lang),
        ) from exc
    except stripe.error.SignatureVerificationError as exc:
        emit_event(
            request,
            action="webhooks.stripe.signature",
            outcome="denied",
            reason="signature_invalid",
            status_code=400,
            provider="stripe",
            error_class=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.signature_invalid", lang),
        ) from exc

    # 017 — idempotency claim: aynı event_id tekrar gelirse 200 + duplicate döner.
    event_id = (event.get("id") if isinstance(event, dict) else None) or ""
    event_type = event["type"]
    evt_row = None
    if event_id:
        try:
            evt_row = claim_event(db, event_id=event_id, event_type=event_type)
        except DuplicateEventError as dup:
            return {
                "status": "ok",
                "type": event_type,
                "duplicate": True,
                "event_id": dup.event_id,
                "license_jti": dup.license_jti,
            }

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        email: str = session.get("customer_email") or (
            session.get("customer_details") or {}
        ).get("email", "")
        stripe_cust: str = session.get("customer", "") or ""
        meta: dict = session.get("metadata") or {}
        tier: str = meta.get("tier", "self-host")
        seat_count: int = _parse_seat_count(meta.get("seat_count"))
        # 023 — Stripe customer locale (e.g. 'tr-TR') ilk 2 char → preferred_lang
        cust_locale = (
            (session.get("customer_details") or {}).get("locale") or ""
        ).lower()
        preferred_lang = (
            cust_locale[:2] if cust_locale[:2] in ("en", "tr", "es") else "en"
        )

        cust_id = stripe_cust or f"email:{email}"

        token = generate_license(
            customer_id=cust_id, tier=tier, seat_count=seat_count
        )
        payload_dict = verify_license(token)

        # idempotency — aynı jti ile daha önce kaydedildiyse atla
        existing = db.scalars(
            select(License).where(License.jti == payload_dict["jti"])
        ).first()
        if existing is not None:
            return {"status": "ok", "jti": payload_dict["jti"], "duplicate": True}

        db_license = License(
            jti=payload_dict["jti"],
            customer_email=email,
            customer_id_stripe=stripe_cust,
            tier=tier,
            seat_count=seat_count,
            issued_at=datetime.fromtimestamp(
                payload_dict["iat"], tz=timezone.utc
            ),
            expires_at=datetime.fromtimestamp(
                payload_dict["exp"], tz=timezone.utc
            ),
            preferred_lang=preferred_lang,
        )
        db.add(db_license)
        db.commit()
        db.refresh(db_license)

        try:
            send_license_email(
                to=email,
                license_key=token,
                refund_url="https://abs.automatiabcn.com/refund",
            )
        except Exception as exc:
            logger.exception("email gönderimi başarısız: %s", exc)

        # 019 — onboarding email serisi (4 email scheduled, first_success ayrı)
        try:
            from app.email.scheduler import schedule_onboarding

            schedule_onboarding(license_jti=payload_dict["jti"], email=email, db=db)
        except Exception as exc:
            logger.exception("onboarding scheduling başarısız: %s", exc)

        # 025 — Discord webhook (no-op if URL not configured)
        try:
            from app.integrations.discord_webhook import notify_license_purchased

            notify_license_purchased(
                jti=payload_dict["jti"],
                email=email,
                tier=tier,
                seat_count=seat_count,
            )
        except Exception as exc:
            logger.info("discord webhook skipped: %s", exc)

        if evt_row is not None:
            mark_processed(db, evt_row, license_jti=payload_dict["jti"])
        return {"status": "ok", "jti": payload_dict["jti"]}

    # 011 — Refund / subscription cancellation: lisansı revoke et
    if event["type"] in ("charge.refunded", "customer.subscription.deleted"):
        obj = event["data"]["object"]
        stripe_cust = obj.get("customer", "") or ""
        metadata = obj.get("metadata") or {}
        target_jti = metadata.get("license_jti")

        license_row = None
        if target_jti:
            license_row = db.scalars(
                select(License).where(License.jti == target_jti)
            ).first()
        elif stripe_cust:
            license_row = db.scalars(
                select(License)
                .where(License.customer_id_stripe == stripe_cust)
                .where(License.revoked_at.is_(None))  # type: ignore[union-attr]
            ).first()

        if license_row is None:
            if evt_row is not None:
                mark_processed(db, evt_row)
            return {
                "status": "ok",
                "type": event["type"],
                "license_found": False,
            }
        if license_row.revoked_at is not None:
            if evt_row is not None:
                mark_processed(db, evt_row, license_jti=license_row.jti)
            return {
                "status": "ok",
                "type": event["type"],
                "duplicate": True,
                "jti": license_row.jti,
            }

        license_row.revoked_at = datetime.now(timezone.utc)
        license_row.revoked_reason = (
            "stripe_refund"
            if event["type"] == "charge.refunded"
            else "stripe_subscription_deleted"
        )
        db.add(license_row)
        db.commit()

        # 012 — İade/iptal onay emaili (sessiz, SMTP yoksa console fallback)
        if license_row.customer_email:
            try:
                from app.email.sender import send_refund_email

                send_refund_email(
                    to=license_row.customer_email,
                    license_jti=license_row.jti,
                    refund_date=license_row.revoked_at.strftime("%Y-%m-%d"),
                )
            except Exception as exc:
                logger.exception("refund email gönderim: %s", exc)

        # 025 — Discord webhook for refund/cancel
        try:
            from app.integrations.discord_webhook import notify_refund

            notify_refund(
                jti=license_row.jti,
                reason=license_row.revoked_reason or "unknown",
            )
        except Exception as exc:
            logger.info("discord refund webhook skipped: %s", exc)

        if evt_row is not None:
            mark_processed(db, evt_row, license_jti=license_row.jti)
        return {
            "status": "ok",
            "type": event["type"],
            "revoked_jti": license_row.jti,
        }

    if evt_row is not None:
        mark_processed(db, evt_row)
    return {"status": "ignored", "type": event["type"]}
