# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stripe Checkout Session creation, called from the landing page.

POST /v1/checkout/create-session
  body: {"sku": "solo" | "team", "customer_email": "x@y.com", "seats": 3}
  → {"checkout_url": "https://checkout.stripe.com/...", "session_id": "cs_..."}

The product is a monthly subscription: Solo is one seat, Team is priced per seat
and starts at three — below that, Solo is cheaper, and offering a two-seat "team"
would only be a way to sell someone the wrong thing.

Stripe Price IDs are read from config (`abs_price_solo`, `abs_price_team`), and
both must be *recurring* monthly prices. They are not created automatically: run
`infra/scripts/setup_stripe_products.py` and paste the resulting IDs into `.env`.
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


# SKU → price resolver. Single source of truth for the mapping.
_SKU_TO_PRICE: dict[str, object] = {
    "solo": lambda: settings.abs_price_solo,
    "team": lambda: settings.abs_price_team,
}

# Team is priced per seat, and starts here. A team of one or two is a Solo
# subscription and costs less.
MIN_TEAM_SEATS = 3


class CreateSessionRequest(BaseModel):
    sku: Literal["solo", "team"] = "solo"
    customer_email: EmailStr
    seats: int = Field(default=1, ge=1, le=500)
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
    price_resolver = _SKU_TO_PRICE[body.sku]
    price_id = price_resolver()  # type: ignore[operator]
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=t("errors.price_id_not_configured", lang, sku=body.sku),
        )

    # Solo is one person by definition; a team starts at three. Trusting the
    # browser's number would let a "team" be bought for one seat at the per-seat
    # price, which is simply a cheaper Solo with a different name on it.
    seat_count = 1 if body.sku == "solo" else max(MIN_TEAM_SEATS, body.seats)

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
            # Seats are the quantity. That is what makes the team plan cost what
            # the pricing page says it costs, and it is what the renewal reads
            # back to decide how many people the next key is for.
            line_items=[{"price": price_id, "quantity": seat_count}],
            customer_email=body.customer_email,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={
                "tier": body.sku,
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
