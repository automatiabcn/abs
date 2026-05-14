# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""031 Modul A — Beta access request portal (public).

POST /v1/beta/request
  body: {email, name, company, use_case, lang}
  - honeypot field `website` MUST be empty (anti-spam, returns 200 silently)
  - 1 request/email/day (DB-side dedupe, not slowapi)
  - auto-approve mode (settings.beta_auto_approve) → license issue + Discord notify
  - manual mode → queue + Discord notify_beta_request
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from app.config import settings
from app.db.models import BetaRequest, License
from app.db.session import get_engine
from app.licensing import generate_license
from app.middleware.rate_limit import limiter


_QUEUED_RESPONSE = {
    "ok": True,
    "status": "queued",
    "check_email": True,
}


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:8]

router = APIRouter(prefix="/v1/beta", tags=["beta"])
logger = logging.getLogger(__name__)


class BetaRequestBody(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=128)
    company: str = Field(default="", max_length=128)
    use_case: str = Field(default="", max_length=1024)
    lang: Literal["en", "tr", "es"] = "en"
    # Honeypot: bots fill it, humans don't see it.
    website: Optional[str] = Field(default="", max_length=256)


def _has_recent_request(email: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with Session(get_engine()) as db:
        existing = db.scalars(
            select(BetaRequest)
            .where(BetaRequest.email == email)
            .where(BetaRequest.created_at >= cutoff)
        ).first()
    return existing is not None


def _persist_request(body: BetaRequestBody) -> BetaRequest:
    row = BetaRequest(
        email=body.email,
        name=body.name,
        company=body.company,
        use_case=body.use_case,
        lang=body.lang,
        status="pending",
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _auto_issue_license(req: BetaRequest) -> str:
    """Issue a 30-day beta license + persist row + schedule beta sequence."""
    import jwt as pyjwt

    token = generate_license(req.email, tier="beta", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            License(
                jti=jti,
                customer_email=req.email,
                tier="beta",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=30),
                preferred_lang=req.lang,
            )
        )
        # Mark request approved
        target = db.scalars(
            select(BetaRequest).where(BetaRequest.id == req.id)
        ).first()
        if target is not None:
            target.status = "approved"
            target.approved_at = now
            target.license_jti = jti
            db.add(target)
        db.commit()
    # Schedule onboarding sequence (idempotent)
    try:
        from app.email.beta_sequence import schedule_beta_sequence

        schedule_beta_sequence(license_jti=jti, customer_email=req.email)
    except Exception as exc:
        logger.warning("beta_sequence schedule failed for %s: %s", jti, exc)
    return jti


def _notify_discord(*, kind: str, req: BetaRequest, jti: Optional[str] = None) -> None:
    """Discord beta-flow notify (no-op if URL unset)."""
    try:
        from app.integrations import discord_webhook as dw

        if kind == "request" and hasattr(dw, "notify_beta_request"):
            dw.notify_beta_request(email=req.email, name=req.name, use_case=req.use_case)
        elif kind == "approved" and hasattr(dw, "notify_beta_approved"):
            dw.notify_beta_approved(license_jti=jti or "", email=req.email)
    except Exception as exc:
        logger.info("discord beta notify failed (%s): %s", kind, exc)


@router.post("/request")
@limiter.limit("3/hour")
async def beta_request(body: BetaRequestBody, request: Request) -> dict:
    """Sprint 2I UAT-022/023/024 — beta intake hardening.

    - Honeypot now logs an 8-char sha256 prefix of the email instead of
      the plaintext PII (UAT-023).
    - Duplicate-recent-request returns the same neutral 200 body as a
      first-time request so the endpoint cannot be used as an email
      enumeration oracle (UAT-024).
    - Auto-approve no longer echoes the license JTI in the response
      body; the customer receives the JTI by email magic-link only
      (UAT-022).
    """
    # Honeypot: silently 200 to bots so they don't retry. Email reduced
    # to an 8-char digest before logging (UAT-023).
    if body.website:
        logger.info("[beta] honeypot triggered email_hash=%s", _email_hash(body.email))
        return _QUEUED_RESPONSE

    if _has_recent_request(body.email):
        # UAT-024 — quiet duplicate. No 429 + no diagnostic body so the
        # endpoint cannot leak which emails are already in the queue.
        logger.info(
            "[beta] duplicate within 24h email_hash=%s", _email_hash(body.email)
        )
        return _QUEUED_RESPONSE

    req = _persist_request(body)

    if settings.beta_auto_approve:
        jti = _auto_issue_license(req)
        _notify_discord(kind="approved", req=req, jti=jti)
        # UAT-022 — JTI travels via the magic-link email only. Response
        # body must not let a public caller harvest tenant identifiers.
        return _QUEUED_RESPONSE

    _notify_discord(kind="request", req=req)
    return _QUEUED_RESPONSE
