# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stripe webhook endpoint.

On `checkout.session.completed` it issues a license, stores it, and emails it
to the customer. Refund and subscription-cancellation events revoke the
license. Every other event type is answered 200 "ignored".
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
from app.observability.audit import emit_event
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# Set once at import: mutating stripe.api_key per request would race.
stripe.api_key = settings.stripe_secret_key

# Cap the webhook body at 1 MiB so an attacker cannot force the worker to
# Buffer a multi-GB POST before the signature check rejects it.
STRIPE_WEBHOOK_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB


def _parse_seat_count(raw) -> int:
    """Parse seat_count from Stripe metadata. Anything unusable yields 1."""
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
    """Verify the signature, then act on the event type."""
    lang = getattr(request.state, "lang", "en")

    # Short-circuit before reading the body when
    # Content-Length advertises an oversize payload so the worker never
    # buffers a multi-GB request.
    content_length_header = request.headers.get("content-length")
    if content_length_header:
        try:
            advertised = int(content_length_header)
        except ValueError:
            advertised = -1
        if advertised > STRIPE_WEBHOOK_MAX_BODY_BYTES:
            emit_event(
                request,
                action="webhooks.stripe.payload",
                outcome="denied",
                reason="payload_too_large",
                status_code=413,
                provider="stripe",
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="payload_too_large",
            )

    payload = await request.body()
    if len(payload) > STRIPE_WEBHOOK_MAX_BODY_BYTES:
        # Defence in depth — chunked transfer can dodge Content-Length.
        emit_event(
            request,
            action="webhooks.stripe.payload",
            outcome="denied",
            reason="payload_too_large",
            status_code=413,
            provider="stripe",
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="payload_too_large",
        )

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

    # Security — Stripe's construct_event uses the secret as the HMAC key with
    # no special-casing for "", so an UNCONFIGURED secret makes every forged
    # signature (computed with an empty key) verify successfully. Fail closed
    # before construct_event — matching billing_v10/webhook_idempotent.py — so
    # a deployment that never set the webhook secret cannot have forged
    # checkout.session.completed events mint licences / trigger emails.
    if not settings.stripe_webhook_secret:
        emit_event(
            request,
            action="webhooks.stripe.signature",
            outcome="denied",
            reason="secret_not_configured",
            status_code=503,
            provider="stripe",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook_not_configured",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError as exc:
        # Exc carries Stripe SDK internals (`Could
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

    # Idempotency claim: a re-sent event_id is answered 200 + duplicate.
    event_id = (event.get("id") if isinstance(event, dict) else None) or ""
    event_type = (event.get("type") if isinstance(event, dict) else None) or ""
    if not event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.signature_invalid", lang),
        )
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

        # Second idempotency layer: the license itself may already be stored.
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

        # The one email that matters. For a self-hosted customer the licence key is
        # the thing they paid for, and it arrives exactly once, by mail.
        #
        # A failure here used to be logged and forgotten: the webhook still returned
        # 200, Stripe was satisfied, the licence row existed, and the customer had a
        # receipt and nothing else. Nobody was told — not the customer, not the
        # operator. It is still not allowed to fail the webhook (Stripe would retry
        # the whole event and re-issue), but it is no longer allowed to be quiet:
        # the failure goes to the audit log, which is the one place that is read
        # when someone writes in asking where their key is, and the key stays
        # recoverable from `POST /v1/admin/licenses/{jti}/resend`.
        try:
            send_license_email(
                to=email,
                license_key=token,
                refund_url="https://abs.automatiabcn.com/refund",
                lang=preferred_lang,
            )
        except Exception as exc:
            logger.critical(
                "LICENCE NOT DELIVERED — paid customer has no key: jti=%s email=%s err=%s",
                payload_dict["jti"], email, exc, exc_info=True,
            )
            try:
                emit_event(
                    None,
                    action="license.delivery_failed",
                    outcome="failure",
                    resource_type="license",
                    resource_id=payload_dict["jti"],
                    user_id=email,
                    reason=str(exc)[:200],
                )
            except Exception:  # noqa: BLE001 — never fail the webhook on the log
                logger.exception("could not record the licence delivery failure")

        # Onboarding series. Delivery failures must not fail the webhook: the
        # License is already issued and Stripe would retry the whole event.
        try:
            from app.email.scheduler import schedule_onboarding

            schedule_onboarding(license_jti=payload_dict["jti"], email=email, db=db)
        except Exception as exc:
            logger.exception("onboarding scheduling failed: %s", exc)

        # Discord webhook (no-op if URL not configured)
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

    # Refund / subscription cancellation: revoke the license.
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

        # Refund/cancellation confirmation email (falls back to console when
        # SMTP is unset; never fails the webhook).
        if license_row.customer_email:
            try:
                from app.email.sender import send_refund_email

                send_refund_email(
                    to=license_row.customer_email,
                    license_jti=license_row.jti,
                    refund_date=license_row.revoked_at.strftime("%Y-%m-%d"),
                )
            except Exception as exc:
                logger.exception("refund email delivery failed: %s", exc)

        # Discord webhook for refund/cancel
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
