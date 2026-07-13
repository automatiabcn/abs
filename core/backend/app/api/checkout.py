# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stripe Checkout Session creation, called from the landing page.

POST /v1/checkout/create-session
  body: {"sku": "self-host" | "team-5" | "team-10", "customer_email": "x@y.com"}
  → {"checkout_url": "https://checkout.stripe.com/...", "session_id": "cs_..."}

Stripe Price IDs are read from config (`abs_price_self_host`,
`abs_price_team_5`, `abs_price_team_10`). They are not created automatically:
run `infra/scripts/setup_stripe_products.py` and paste the resulting IDs
into `.env`.
"""

from __future__ import annotations

import logging
from typing import Literal

import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.i18n import t
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/v1/checkout", tags=["checkout"])
logger = logging.getLogger(__name__)


# SKU → (price_id resolver, seat_count). Single source of truth for the mapping.
_SKU_TO_PRICE: dict[str, tuple] = {
    "self-host": (lambda: settings.abs_price_self_host, 1),
    "team-5": (lambda: settings.abs_price_team_5, 5),
    "team-10": (lambda: settings.abs_price_team_10, 10),
}


class CreateSessionRequest(BaseModel):
    sku: Literal["self-host", "team-5", "team-10"] = "self-host"
    customer_email: EmailStr
    success_url: str = Field(default="https://abs.automatiabcn.com/thanks")
    cancel_url: str = Field(default="https://abs.automatiabcn.com/")


class CreateSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


@router.post("/create-session", response_model=CreateSessionResponse)
@limiter.limit("10/minute")
async def create_session(
    request: Request, body: CreateSessionRequest
) -> CreateSessionResponse:
    lang = getattr(request.state, "lang", "en")
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503, detail=t("errors.stripe_not_configured", lang)
        )
    price_resolver, seat_count = _SKU_TO_PRICE[body.sku]
    price_id = price_resolver()
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=t("errors.price_id_not_configured", lang, sku=body.sku),
        )

    stripe.api_key = settings.stripe_secret_key
    try:
        # A recurring price must be sold in subscription mode; Stripe refuses it in
        # payment mode, and a one-time price refuses subscription mode. The mode was
        # hardcoded to "payment", so the moment an annual (renewing) price is wired
        # to a SKU here, checkout would break — or, worse, keep working against a
        # price that was quietly created as one-time. Ask the price what it is.
        mode = "payment"
        try:
            price = stripe.Price.retrieve(price_id)
            if getattr(price, "recurring", None):
                mode = "subscription"
        except Exception:  # noqa: BLE001 — an unreadable price is not a reason to
            pass  # refuse a sale; the Session.create below will still fail loudly

        session = stripe.checkout.Session.create(
            mode=mode,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=body.customer_email,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={
                "tier": "self-host" if body.sku == "self-host" else "team",
                "seat_count": str(seat_count),
                "sku": body.sku,
            },
        )
    except stripe.error.StripeError as exc:
        # Log full exception internally; return only the
        # Stripe-curated user_message (or a generic fallback) to the
        # client. str(exc) can leak account-internal IDs (cus_*, sub_*,
        # acct_*) that adversaries can fingerprint.
        logger.exception("checkout session create failed: %s", exc)
        msg = getattr(exc, "user_message", None) or "stripe_unavailable"
        raise HTTPException(status_code=502, detail=f"Stripe error: {msg}") from exc

    url = getattr(session, "url", None) or (
        session.get("url") if isinstance(session, dict) else None
    )
    sid = getattr(session, "id", None) or (
        session.get("id") if isinstance(session, dict) else None
    )
    if not url or not sid:
        raise HTTPException(status_code=502, detail="Stripe session response invalid")
    return CreateSessionResponse(checkout_url=url, session_id=sid)
