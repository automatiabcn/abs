# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Getting a paid customer their licence key when the email did not arrive.

The key is delivered once, by email, at the moment Stripe confirms payment. If that
send fails — a mail server down for a minute, a typo'd SMTP password, a bounce — the
customer has a receipt and nothing else. The webhook cannot retry the send by failing
(Stripe would replay the whole event and re-issue the licence), so until now the
failure was written to a log nobody reads and the customer wrote in to support.

This is the way back: an operator looks up the licence and sends it again. The key is
re-minted from the licence row rather than stored — a signed key at rest is a signed
key to steal — and the resend is recorded in the audit log, because sending someone's
licence key to an address is exactly the kind of thing that should leave a mark.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.admin.auth import admin_required
from app.db.models import License
from app.db.session import get_engine
from app.email.sender import send_license_email
from app.licensing import generate_license
from app.observability.audit import emit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/licenses", tags=["admin"])


@router.post("/{jti}/resend")
async def resend_license(jti: str, admin: dict = Depends(admin_required)) -> dict:
    """Mint the customer's key again and email it to them."""
    with Session(get_engine()) as db:
        lic = db.exec(select(License).where(License.jti == jti)).first()
        if lic is None:
            raise HTTPException(404, "license_not_found")
        email = lic.customer_email
        token = generate_license(
            customer_id=lic.customer_id_stripe or f"email:{email}",
            tier=lic.tier,
            seat_count=lic.seat_count,
        )

    try:
        send_license_email(
            to=email,
            license_key=token,
            refund_url="https://abs.automatiabcn.com/refund",
            lang=getattr(lic, "preferred_lang", "en") or "en",
        )
    except Exception as exc:  # noqa: BLE001 — a failed send is the answer, not a 500
        logger.warning("licence resend failed: jti=%s err=%s", jti, exc)
        emit_event(
            None,
            action="license.resend",
            outcome="failure",
            resource_type="license",
            resource_id=jti,
            user_id=str(admin.get("email") or admin.get("sub") or "admin"),
            reason=str(exc)[:200],
        )
        raise HTTPException(502, f"the licence key could not be sent: {exc}"[:300])

    emit_event(
        None,
        action="license.resend",
        outcome="success",
        resource_type="license",
        resource_id=jti,
        user_id=str(admin.get("email") or admin.get("sub") or "admin"),
    )
    return {"ok": True, "jti": jti, "sent_to": email}
