"""029 Modul D — Customer-facing consent API.

GET    /v1/me/consents                 — list all consents
POST   /v1/me/consents                 — grant {consent_type, version}
DELETE /v1/me/consents/{consent_type}  — withdraw
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.customer_audit.consent import (
    CONSENT_TYPES,
    grant_consent,
    list_consents,
    withdraw_consent,
)
from app.customer_audit.logger import log_customer_action
from app.licensing import verify_license

router = APIRouter(prefix="/v1/me", tags=["me"])
logger = logging.getLogger(__name__)


def _verify_bearer_license(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization Bearer license required")
    token = authorization.split(None, 1)[1].strip()
    try:
        payload = verify_license(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, f"License verify failed: {exc}") from exc
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(401, "Token missing jti")
    return jti


class GrantBody(BaseModel):
    consent_type: str
    version: str = "1.0"
    source: str = "panel"


@router.get("/consents")
async def get_consents(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    jti = _verify_bearer_license(authorization)
    return {"license_jti": jti, "consents": list_consents(license_jti=jti)}


@router.post("/consents")
async def post_consent(
    body: GrantBody,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    jti = _verify_bearer_license(authorization)
    if body.consent_type not in CONSENT_TYPES:
        raise HTTPException(400, f"unknown consent_type: {body.consent_type}")
    row = grant_consent(
        license_jti=jti,
        consent_type=body.consent_type,
        version=body.version,
        source=body.source,
    )
    log_customer_action(
        license_jti=jti,
        action="consent.granted",
        resource=body.consent_type,
        detail=f"version={body.version}",
    )
    return {
        "ok": True,
        "consent_type": row.consent_type,
        "version": row.version,
        "granted_at": row.granted_at.isoformat() if row.granted_at else None,
    }


@router.delete("/consents/{consent_type}")
async def delete_consent(
    consent_type: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    jti = _verify_bearer_license(authorization)
    if consent_type not in CONSENT_TYPES:
        raise HTTPException(400, f"unknown consent_type: {consent_type}")
    row = withdraw_consent(license_jti=jti, consent_type=consent_type)
    if row is None:
        raise HTTPException(404, "consent_not_found")
    log_customer_action(
        license_jti=jti,
        action="consent.withdrawn",
        resource=consent_type,
    )
    return {
        "ok": True,
        "consent_type": row.consent_type,
        "withdrawn_at": row.withdrawn_at.isoformat() if row.withdrawn_at else None,
    }
