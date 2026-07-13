# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stripe Customer Portal: customer self-service (license, invoices, refunds).

POST /v1/billing/portal
  body: {"customer_email": "x@y.com", "return_url": "..."}
  → {"portal_url": "https://billing.stripe.com/...", "expires_at": ISO8601}

Flow:
1. Find the active license (revoked_at IS NULL) for customer_email.
2. Open a stripe.billing_portal.Session with its License.customer_id_stripe.
3. Return the portal URL. Stripe expires these after roughly an hour.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from app.config import settings
from app.db.models import License
from app.db.session import get_session
from app.i18n import t
from app.middleware.rate_limit import limiter
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/billing", tags=["billing"])
logger = logging.getLogger(__name__)


class PortalRequest(BaseModel):
    customer_email: EmailStr
    return_url: str = "https://abs.automatiabcn.com/"


class PortalResponse(BaseModel):
    portal_url: str
    expires_at: str


@router.post("/portal", response_model=PortalResponse)
@limiter.limit("10/minute")
async def create_portal(
    request: Request,
    body: PortalRequest,
    db: Session = Depends(get_session),
) -> PortalResponse:
    lang = getattr(request.state, "lang", "en")
    if not settings.stripe_secret_key:
        emit_event(
            request,
            action="billing.portal.create",
            outcome="denied",
            reason="stripe_not_configured",
            status_code=503,
        )
        raise HTTPException(
            status_code=503, detail=t("errors.stripe_not_configured", lang)
        )

    license_row = db.scalars(
        select(License)
        .where(License.customer_email == body.customer_email)
        .where(License.revoked_at.is_(None))  # type: ignore[union-attr]
    ).first()

    if license_row is None or not license_row.customer_id_stripe:
        emit_event(
            request,
            action="billing.portal.create",
            outcome="denied",
            reason="license_not_found",
            status_code=404,
        )
        raise HTTPException(status_code=404, detail=t("errors.license_not_found", lang))

    stripe.api_key = settings.stripe_secret_key
    try:
        portal = stripe.billing_portal.Session.create(
            customer=license_row.customer_id_stripe,
            return_url=body.return_url,
        )
    except stripe.error.StripeError as exc:
        # Internal-only str(exc); client-facing detail is
        # the Stripe-curated user_message or the i18n generic message.
        # Prevents leakage of account-internal IDs / API key prefixes.
        logger.exception("portal session create failed: %s", exc)
        safe_detail = getattr(exc, "user_message", None) or "stripe_unavailable"
        emit_event(
            request,
            action="billing.portal.create",
            outcome="error",
            reason="stripe_error",
            error_class=type(exc).__name__,
            status_code=502,
        )
        raise HTTPException(
            status_code=502,
            detail=t("errors.portal_create_failed", lang, detail=safe_detail),
        ) from exc

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    url = getattr(portal, "url", None)
    if url is None and isinstance(portal, dict):
        url = portal.get("url")
    if not url:
        emit_event(
            request,
            action="billing.portal.create",
            outcome="error",
            reason="portal_response_invalid",
            status_code=502,
        )
        raise HTTPException(
            status_code=502, detail=t("errors.portal_response_invalid", lang)
        )

    emit_event(
        request,
        action="billing.portal.create",
        outcome="success",
        license_id=license_row.id,
        status_code=200,
    )
    return PortalResponse(portal_url=url, expires_at=expires.isoformat())
