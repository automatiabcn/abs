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
from app.observability.audit import emit_event  # Q12-L22 sweep 2
from app.vault.audit_chain import stats as audit_stats
from app.vault.rotation import RotationBusyError, RotationError, rotate_age_key

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
    except RotationBusyError as exc:
        # Q12-L22-002 — concurrent rotate guard. Distinct status (409)
        # so ops can alert separately from genuine rotation failures.
        emit_event(
            request,
            action="admin.vault.rotate",
            outcome="denied",
            reason="rotation_in_progress",
            status_code=409,
            provider="vault",
        )
        raise HTTPException(409, "rotation_in_progress") from exc
    except RotationError as exc:
        emit_event(
            request,
            action="admin.vault.rotate",
            outcome="error",
            reason="rotation_failed",
            status_code=500,
            provider="vault",
            error_class=type(exc).__name__,
        )
        # Keep response generic — exc message can carry sops/age cli stderr.
        raise HTTPException(500, "rotation_failed") from exc
    emit_event(
        request,
        action="admin.vault.rotate",
        outcome="success",
        provider="vault",
        count=int(result.get("secrets_re_encrypted") or 0),
        duration_ms=float(result.get("elapsed_ms") or 0),
    )
    return result


@router.get("/audit")
async def audit(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    limit: int = 50,
) -> dict:
    _check_admin(authorization, request)
    return audit_stats(recent_limit=limit)
