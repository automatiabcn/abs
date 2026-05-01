"""027 Modul B — Vault admin endpoints.

POST /v1/admin/vault/rotate-key   — rotate age master key (Bearer admin auth)
GET  /v1/admin/vault/audit         — recent audit entries + integrity (Bearer)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.vault.audit_chain import stats as audit_stats
from app.vault.rotation import RotationError, rotate_age_key

router = APIRouter(prefix="/v1/admin/vault", tags=["admin-vault"])
logger = logging.getLogger(__name__)


def _panel_session_is_admin(request: Optional[Request]) -> bool:
    """CJ-010 — bootstrap/single-admin self-host icin panel oturumu kabul et."""
    if request is None:
        return False
    try:
        from app.api import auth as panel_auth_mod

        token = request.cookies.get(panel_auth_mod.COOKIE_NAME, "")
        if not token:
            return False
        payload = panel_auth_mod._decode_token(token)
        admin_email, _hash, _src = panel_auth_mod._load_admin_credentials()
        return payload.get("sub") == admin_email
    except Exception:
        return False


def _check_admin(
    authorization: Optional[str], request: Optional[Request] = None
) -> None:
    if _panel_session_is_admin(request):
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization header missing")
    token = authorization.split(None, 1)[1].strip()
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(403, "Invalid admin token")


class RotateRequest(BaseModel):
    reason: str = "manual"


@router.post("/rotate-key")
async def rotate_key(
    body: RotateRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _check_admin(authorization, request)
    try:
        result = rotate_age_key(reason=body.reason, actor="admin-api")
    except RotationError as exc:
        raise HTTPException(500, f"Rotation failed: {exc}") from exc
    return result


@router.get("/audit")
async def audit(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    limit: int = 50,
) -> dict:
    _check_admin(authorization, request)
    return audit_stats(recent_limit=limit)
