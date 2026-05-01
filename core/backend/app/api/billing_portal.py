"""017 — Stripe Customer Portal: müşteri self-service (lisans, fatura, iade).

POST /v1/billing/portal
  body: {"customer_email": "x@y.com", "return_url": "..."}
  → {"portal_url": "https://billing.stripe.com/...", "expires_at": ISO8601}

Akış:
1. customer_email ile aktif lisansı (revoked_at IS NULL) bul
2. License.customer_id_stripe ile stripe.billing_portal.Session.create
3. Portal URL döner (Stripe varsayılan ~1 saat geçerli)
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

router = APIRouter(prefix="/v1/billing", tags=["billing"])
logger = logging.getLogger(__name__)


class PortalRequest(BaseModel):
    customer_email: EmailStr
    return_url: str = "https://abs.automatiabcn.com/"


class PortalResponse(BaseModel):
    portal_url: str
    expires_at: str


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    body: PortalRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> PortalResponse:
    lang = getattr(request.state, "lang", "en")
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503, detail=t("errors.stripe_not_configured", lang)
        )

    license_row = db.scalars(
        select(License)
        .where(License.customer_email == body.customer_email)
        .where(License.revoked_at.is_(None))  # type: ignore[union-attr]
    ).first()

    if license_row is None or not license_row.customer_id_stripe:
        raise HTTPException(
            status_code=404, detail=t("errors.license_not_found", lang)
        )

    stripe.api_key = settings.stripe_secret_key
    try:
        portal = stripe.billing_portal.Session.create(
            customer=license_row.customer_id_stripe,
            return_url=body.return_url,
        )
    except stripe.error.StripeError as exc:
        logger.exception("portal session create failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=t("errors.portal_create_failed", lang, detail=str(exc)[:200]),
        ) from exc

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    url = getattr(portal, "url", None)
    if url is None and isinstance(portal, dict):
        url = portal.get("url")
    if not url:
        raise HTTPException(
            status_code=502, detail=t("errors.portal_response_invalid", lang)
        )

    return PortalResponse(portal_url=url, expires_at=expires.isoformat())
