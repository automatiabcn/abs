# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Minting the next month's key — the seller's half of a monthly subscription.

A customer's server runs offline and checks its licence against a signature, not
against us. That is the whole point, and it is also why the key has to be short:
a key that lasts a year cannot tell that the subscription was cancelled in month
two. So each key is minted to last exactly as long as the period the customer has
paid for, plus the grace window, and a few days before it runs out their server
asks here for the next one.

This endpoint answers one question, and it asks Stripe rather than a table:
*is this subscription still alive right now?* The subscription is the truth.
Webhooks arrive late, arrive twice, and occasionally do not arrive at all, and a
customer whose renewal hinges on an event we may have missed is a customer whose
server goes dark for a reason they cannot see and we cannot explain.

Nothing here is a decision about someone else's data. A subscription that has
ended gets a plain 402 and no key; the server that asked keeps working until its
current key runs out, and then pauses chat while leaving every document,
transcript and provider key exactly where the customer left it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import settings
from app.db.models import License
from app.db.session import get_engine
from app.licensing.gate import GRACE_DAYS
from app.licensing.generator import generate_license

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/license", tags=["license"])

# A subscription in any of these states has been paid for, or is inside the
# window Stripe itself gives a failed card to recover. `past_due` is deliberate:
# the customer's card bounced, Stripe is retrying, and taking their server away
# on the first failed retry would be a cruel way to find out about an expired
# card.
_LIVE_STATES = {"active", "trialing", "past_due"}

_INACTIVE = (
    "Your subscription is no longer active, so no new licence was issued. Chat "
    "and the agent will pause when the current key runs out. Everything on the "
    "server stays yours — documents, transcripts and keys can still be read, "
    "exported and deleted. Subscribe again from the panel, under "
    "Settings → Licence."
)


class RenewRequest(BaseModel):
    license_key: str = Field(..., min_length=10, max_length=4096)


def _claims(token: str) -> Dict[str, Any]:
    """The presented key's claims. The signature is checked separately, and an
    expired key is exactly the key we expect to be handed here."""
    try:
        return dict(
            pyjwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
        )
    except Exception:  # noqa: BLE001
        return {}


def _verified_jti(token: str) -> Optional[str]:
    """Only a key we actually minted may ask for another one.

    Verified for *signature*, not for expiry — a renewal request arrives from a
    server whose key is running out, and sometimes from one whose key ran out
    while the machine was switched off.
    """
    try:
        public_key = open(settings.public_key_path, "rb").read()
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        return str(payload.get("jti") or "") or None
    except Exception as exc:  # noqa: BLE001
        logger.info("renew_rejected reason=bad_signature err=%s", exc)
        return None


def _subscription_for(customer_id: str) -> Optional[Dict[str, Any]]:
    """The customer's live subscription, straight from Stripe."""
    import stripe

    stripe.api_key = settings.stripe_secret_key
    subs = stripe.Subscription.list(customer=customer_id, status="all", limit=10)
    for sub in subs.get("data", []):
        if sub.get("status") in _LIVE_STATES:
            return dict(sub)
    return None


def _seats_on(sub: Dict[str, Any]) -> int:
    """What the customer is paying for this month.

    Read off the subscription rather than off the old key: an admin who added
    three seats last week is paying for them now, and the key that arrives has to
    say so or the seat gate will refuse the people they just bought room for.
    """
    items = (sub.get("items") or {}).get("data") or []
    total = sum(int(item.get("quantity") or 0) for item in items)
    return max(1, total)


@router.post("/renew", status_code=status.HTTP_200_OK)
async def renew_license(body: RenewRequest, request: Request) -> Dict[str, Any]:
    """Issue the next key for a subscription that is still alive."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="billing_not_configured")

    jti = _verified_jti(body.license_key.strip())
    if not jti:
        raise HTTPException(status_code=401, detail="bad_signature")

    with Session(get_engine()) as db:
        row = db.exec(select(License).where(License.jti == jti)).first()

    if row is None:
        # Signed by us, unknown to us. Not a licence we can renew.
        raise HTTPException(status_code=404, detail="unknown_license")

    if row.revoked_at is not None:
        # A refunded or cancelled licence does not get a fresh key by asking
        # again from a different machine.
        logger.info("renew_refused jti=%s reason=revoked", jti)
        raise HTTPException(status_code=402, detail=_INACTIVE)

    customer_id = (row.customer_id_stripe or "").strip()
    if not customer_id:
        raise HTTPException(status_code=402, detail=_INACTIVE)

    try:
        sub = _subscription_for(customer_id)
    except Exception as exc:  # noqa: BLE001
        # Our problem, not theirs. A 503 tells the customer's server to try again
        # later; it has days of key left and a grace window behind that, so
        # nothing stops because Stripe was slow.
        logger.warning("renew_stripe_unreachable jti=%s err=%s", jti, exc)
        raise HTTPException(status_code=503, detail="billing_unreachable") from exc

    if sub is None:
        logger.info("renew_refused jti=%s reason=no_live_subscription", jti)
        raise HTTPException(status_code=402, detail=_INACTIVE)

    period_end = sub.get("current_period_end")
    if not isinstance(period_end, (int, float)):
        raise HTTPException(status_code=502, detail="subscription_has_no_period_end")

    seats = _seats_on(sub)
    claims = _claims(body.license_key)
    tier = str(claims.get("tier") or row.tier or "solo")

    # Exactly the month they have paid for, plus the grace window — so a renewal
    # that fails for a few days (our outage, their firewall) costs the customer
    # nothing, and a subscription that genuinely ends runs out on its own without
    # anyone having to reach the machine.
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(float(period_end), tz=timezone.utc)
    valid_days = max(1, int((expires_at - now).total_seconds() // 86400) + GRACE_DAYS)

    token = generate_license(
        customer_id=customer_id,
        tier=tier,
        seat_count=seats,
        valid_days=valid_days,
    )
    fresh = _claims(token)

    with Session(get_engine()) as db:
        db.add(
            License(
                jti=str(fresh["jti"]),
                customer_email=row.customer_email,
                customer_id_stripe=customer_id,
                tier=tier,
                seat_count=seats,
                issued_at=datetime.fromtimestamp(float(fresh["iat"]), tz=timezone.utc),
                expires_at=datetime.fromtimestamp(float(fresh["exp"]), tz=timezone.utc),
                preferred_lang=row.preferred_lang,
            )
        )
        db.commit()

    logger.info(
        "license_renewed customer=%s old_jti=%s new_jti=%s seats=%d",
        customer_id,
        jti,
        fresh.get("jti"),
        seats,
    )
    return {"license_key": token, "expires_at": fresh.get("exp"), "seat_count": seats}
