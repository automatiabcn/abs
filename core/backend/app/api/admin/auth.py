"""032 Modul A — Admin auth (separate from /auth panel cookie session).

POST /v1/admin/login {password}
  → 200 { token, expires_in_seconds }
  → 401 wrong password
  → 403 IP not whitelisted
  → 503 admin_password_hash unset (login disabled)

Bearer JWT (24h) is used by all /v1/admin/* endpoints. Cookie copy is
HttpOnly+Secure+SameSite=Strict for an admin SPA later.

bcrypt password verification (no plain-text storage). Plain password is
never logged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)

ADMIN_COOKIE = "abs_admin"
JWT_TTL_SECONDS = 24 * 60 * 60

# In-memory rate limiter: 5 failed attempts / 15min per IP.
_FAIL_WINDOW_SECONDS = 15 * 60
_FAIL_LIMIT = 5
_failures: dict[str, list[float]] = {}


def _whitelist_ips() -> list[str]:
    raw = (settings.admin_ip_whitelist or "").strip()
    if not raw:
        return []
    return [ip.strip() for ip in raw.split(",") if ip.strip()]


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _ip_allowed(ip: str) -> bool:
    wl = _whitelist_ips()
    return not wl or ip in wl


def _record_failure(ip: str) -> None:
    now = time.time()
    bucket = [t for t in _failures.get(ip, []) if now - t < _FAIL_WINDOW_SECONDS]
    bucket.append(now)
    _failures[ip] = bucket


def _too_many_failures(ip: str) -> bool:
    now = time.time()
    bucket = [t for t in _failures.get(ip, []) if now - t < _FAIL_WINDOW_SECONDS]
    _failures[ip] = bucket
    return len(bucket) >= _FAIL_LIMIT


def _verify_password(raw: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _issue_jwt() -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(seconds=JWT_TTL_SECONDS)).timestamp())
    token = pyjwt.encode(
        {
            "sub": "admin",
            "iat": int(now.timestamp()),
            "exp": exp,
            "scope": "admin",
        },
        settings.admin_jwt_secret,
        algorithm="HS256",
    )
    return token, exp


def verify_admin_jwt(token: str) -> dict:
    try:
        payload = pyjwt.decode(
            token, settings.admin_jwt_secret, algorithms=["HS256"]
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "admin_token_expired") from exc
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(401, "admin_token_invalid") from exc
    if payload.get("scope") != "admin":
        raise HTTPException(403, "admin_scope_required")
    return payload


def _try_panel_session(request: Request) -> Optional[dict]:
    """CJ-010 — fallback: panel session JWT (abs_session) bootstrap admin
    veya admin_credentials.json'da kayitli email ise admin scope ver.
    Self-host single-admin senaryosunda panel oturumuyla /v1/admin/* erisilebilir.
    """
    from app.api import auth as panel_auth_mod

    panel_token = request.cookies.get(panel_auth_mod.COOKIE_NAME, "")
    if not panel_token:
        return None
    try:
        payload = panel_auth_mod._decode_token(panel_token)
    except HTTPException:
        return None
    sub = payload.get("sub", "")
    try:
        admin_email, _hash, _source = panel_auth_mod._load_admin_credentials()
    except Exception:
        return None
    if sub and sub == admin_email:
        return {
            "sub": sub,
            "exp": payload.get("exp"),
            "scope": "admin",
            "via": "panel_session",
        }
    return None


def admin_required(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """FastAPI dependency for /v1/admin/* routes.

    Accepts (in priority order):
      1. Authorization: Bearer <admin-jwt>
      2. HttpOnly cookie 'abs_admin' (admin SPA)
      3. Panel session cookie 'abs_session' if email matches admin_credentials
         (CJ-010 — bootstrap/single-admin self-host)

    Enforces optional IP whitelist.
    """
    ip = _client_ip(request)
    if not _ip_allowed(ip):
        raise HTTPException(403, "admin_ip_not_whitelisted")

    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1].strip()
    if not token:
        token = request.cookies.get(ADMIN_COOKIE, "")

    if token:
        return verify_admin_jwt(token)

    # CJ-010 — panel session fallback (single-admin self-host)
    panel = _try_panel_session(request)
    if panel:
        return panel

    raise HTTPException(401, "admin_bearer_or_cookie_required")


class LoginBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=256)


@router.post("/login")
async def admin_login(
    body: LoginBody, request: Request, response: Response
) -> dict:
    if not settings.admin_password_hash:
        raise HTTPException(503, "admin_login_disabled")
    ip = _client_ip(request)
    if not _ip_allowed(ip):
        raise HTTPException(403, "admin_ip_not_whitelisted")
    if _too_many_failures(ip):
        raise HTTPException(429, "admin_login_rate_limited")

    if not _verify_password(body.password, settings.admin_password_hash):
        _record_failure(ip)
        # CRITICAL: never log the submitted password
        logger.warning("admin login failed ip=%s", ip)
        raise HTTPException(401, "admin_password_invalid")

    token, exp = _issue_jwt()
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=(settings.env == "prod"),
        path="/",
    )
    return {
        "token": token,
        "expires_in_seconds": JWT_TTL_SECONDS,
        "expires_at": exp,
    }


@router.post("/logout")
async def admin_logout(response: Response, _admin: dict = Depends(admin_required)) -> dict:
    response.delete_cookie(key=ADMIN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def admin_me(payload: dict = Depends(admin_required)) -> dict:
    return {"sub": payload.get("sub"), "exp": payload.get("exp")}


def _reset_state_for_tests() -> None:
    """Helper for tests to clear the in-memory rate-limit bucket."""
    _failures.clear()
