# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

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
from app.observability.audit import emit_event  # Q12-L23 sweep 4

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
    """Resolve the caller IP for the admin IP-whitelist gate and the
    in-memory brute-force lockout bucket.

    SECURITY (auth/session round): this MUST NOT blindly trust the
    client-supplied ``X-Forwarded-For`` header. The previous implementation
    took ``XFF[0]`` unconditionally, which let any caller:
      (a) bypass ``admin_ip_whitelist`` by sending
          ``X-Forwarded-For: <whitelisted-ip>`` from anywhere; and
      (b) reset the per-IP lockout bucket on every request by rotating the
          header, turning the bcrypt admin password into an unthrottled
          brute-force target (``/v1/admin/login`` has no slowapi decorator —
          ``_too_many_failures`` keyed on this IP is its only throttle).

    We defer to the same trusted-proxy gate the rate-limiter already uses
    (UAT-042): ``X-Forwarded-For`` is honoured only when the immediate hop
    (``request.client.host``) is listed in ``ABS_TRUSTED_PROXIES``; otherwise
    the raw socket address is used and the header is ignored.
    """
    from app.middleware.rate_limit import client_ip_for_rate_limit

    return client_ip_for_rate_limit(request)


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


def _is_active_admin_user(email: str) -> bool:
    """Multi-admin RBAC — true when ``email`` belongs to an active users-table
    row whose role is ``admin``. This is what makes the panel's role dropdown
    (promote/demote) actually grant or revoke admin powers: pre-fix only the
    bootstrap admin (admin_credentials.json) could reach /v1/admin/*, so
    promoting a second user to "admin" changed a label but nothing else.

    Security: only ``status == "active"`` AND ``role == "admin"`` qualifies.
    Public self-signup deliberately creates ``role="member"`` rows (see
    app/api/auth._persist_user_pending), so this cannot be self-escalated;
    the admin role is reachable only via the bootstrap admin or an explicit
    admin invite that the recipient has claimed.
    """
    if not email:
        return False
    try:
        from sqlmodel import Session, select

        from app.db.models import User
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            user = db.exec(select(User).where(User.email == email)).first()
            return bool(
                user and user.role == "admin" and user.status == "active"
            )
    except Exception as exc:  # pragma: no cover — defensive only
        logger.debug("active-admin lookup skipped (non-fatal): %s", exc)
        return False


def _try_panel_session(request: Request) -> Optional[dict]:
    """CJ-010 — fallback: panel session JWT (abs_session) grants admin scope to
    the bootstrap admin (admin_credentials.json) OR to any active users-table
    row with role=="admin" (multi-admin, added so the panel role dropdown is
    authoritative). Self-host single- and multi-admin both reach /v1/admin/*
    with just their panel login.
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
    # 1. Bootstrap admin (admin_credentials.json) — single-admin self-host.
    try:
        admin_email, _hash, _source = panel_auth_mod._load_admin_credentials()
    except Exception:
        admin_email = None
    if sub and sub == admin_email:
        return {
            "sub": sub,
            "exp": payload.get("exp"),
            "scope": "admin",
            "via": "panel_session",
        }
    # 2. Multi-admin — active users-table row promoted to role=="admin".
    if sub and _is_active_admin_user(sub):
        return {
            "sub": sub,
            "exp": payload.get("exp"),
            "scope": "admin",
            "via": "panel_session_role",
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
        emit_event(
            request,
            action="admin.auth.gate",
            outcome="denied",
            reason="ip_not_whitelisted",
            status_code=403,
            ip=ip,
        )
        raise HTTPException(403, "admin_ip_not_whitelisted")

    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1].strip()
    if not token:
        token = request.cookies.get(ADMIN_COOKIE, "")

    if token:
        # Q12-L23 sweep 4 — wrap so JWT exp/invalid/scope denials emit audit.
        try:
            return verify_admin_jwt(token)
        except HTTPException as exc:
            emit_event(
                request,
                action="admin.auth.gate",
                outcome="denied",
                reason=str(exc.detail or "admin_jwt_rejected"),
                status_code=exc.status_code,
                ip=ip,
            )
            raise

    # CJ-010 — panel session fallback (single-admin self-host)
    panel = _try_panel_session(request)
    if panel:
        emit_event(
            request,
            action="admin.auth.gate",
            outcome="success",
            reason="panel_session_fallback",
            ip=ip,
        )
        return panel

    emit_event(
        request,
        action="admin.auth.gate",
        outcome="denied",
        reason="missing_bearer_and_cookie",
        status_code=401,
        ip=ip,
    )
    raise HTTPException(401, "admin_bearer_or_cookie_required")


class LoginBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=256)


@router.post("/login")
async def admin_login(
    body: LoginBody, request: Request, response: Response
) -> dict:
    ip = _client_ip(request)
    if not settings.admin_password_hash:
        emit_event(
            request,
            action="admin.login",
            outcome="denied",
            reason="login_disabled_no_password_hash",
            status_code=503,
            ip=ip,
        )
        raise HTTPException(503, "admin_login_disabled")
    if not _ip_allowed(ip):
        emit_event(
            request,
            action="admin.login",
            outcome="denied",
            reason="ip_not_whitelisted",
            status_code=403,
            ip=ip,
        )
        raise HTTPException(403, "admin_ip_not_whitelisted")
    if _too_many_failures(ip):
        emit_event(
            request,
            action="admin.login",
            outcome="denied",
            reason="rate_limited",
            status_code=429,
            ip=ip,
        )
        raise HTTPException(429, "admin_login_rate_limited")

    if not _verify_password(body.password, settings.admin_password_hash):
        _record_failure(ip)
        # CRITICAL: never log the submitted password
        logger.warning("admin login failed ip=%s", ip)
        emit_event(
            request,
            action="admin.login",
            outcome="failure",
            reason="password_invalid",
            status_code=401,
            ip=ip,
        )
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
    emit_event(
        request,
        action="admin.login",
        outcome="success",
        ip=ip,
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
