# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""OAuth 2.1 endpoints (FastAPI router).

Mounted at app root by `app.main`. Endpoints:
    GET  /oauth/authorize          → returns 302 redirect with `code`
    POST /oauth/token              → grant_type=authorization_code|refresh_token
    GET  /.well-known/jwks.json    → JWKS document
    GET  /.well-known/openid-configuration → OIDC discovery (subset)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlmodel import Session

from app.auth.events import publish_login_failed, publish_login_success
from app.auth.oauth.jwks import jwks_document
from app.auth.oauth.server import (
    OAuthError,
    exchange_code_for_tokens,
    issue_authorization_code,
    refresh_access_token,
)
from app.config import settings
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["oauth"])

ISSUER = "https://abs.local"


def _err_response(exc: OAuthError, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": exc.code, "error_description": exc.description},
        status_code=status,
    )


def _resolve_roles(subject: str) -> list[str]:
    """Roles for an OAuth token minted from an authenticated session.

    Derived from the users-table ``role`` (with a bootstrap-admin overlay),
    NEVER from a caller-supplied ``roles`` query param. This is what prevents
    an authenticated low-privilege user from escalating via
    ``/oauth/authorize?roles=admin``.
    """
    try:
        from sqlmodel import Session as _S
        from sqlmodel import select

        from app.db.models import User
        from app.db.session import get_engine

        with _S(get_engine()) as db:
            u = db.execute(select(User).where(User.email == subject)).scalars().first()
            if u is not None and u.role:
                return [str(u.role)]
    except Exception:  # pragma: no cover — defensive
        pass
    try:
        from app.api.auth import _load_admin_credentials

        admin_email, _h, _s = _load_admin_credentials()
        if subject and subject == admin_email:
            return ["admin"]
    except Exception:  # pragma: no cover — defensive
        pass
    return ["member"]


def _session_principal(request: Request):
    """Resolve ``(subject, tenant, roles)`` from a valid, non-revoked
    ``abs_session`` panel cookie, or ``None`` when there is no such session.

    This is the authoritative identity source for ``/oauth/authorize``: the
    subject must be proven by a real login, not asserted by the caller.
    """
    from app.api.auth import (
        COOKIE_NAME,
        _SessionExpired,
        _SessionInvalid,
        _decode_token,
        _subject_revoked,
    )

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        claims = _decode_token(token)
    except (_SessionExpired, _SessionInvalid):
        return None
    sub = str(claims.get("sub") or "")
    if not sub or _subject_revoked(sub):
        return None
    return sub, claims.get("tenant"), _resolve_roles(sub)


@router.get("/oauth/authorize", include_in_schema=False)
async def authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(""),
    state: Optional[str] = Query(None),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    nonce: Optional[str] = Query(None),
    user_subject: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    roles: Optional[str] = Query(None, description="comma-separated"),
    db: Session = Depends(get_session),
) -> Response:
    """Issue an authorization code.

    NOTE: in this MVP `user_subject` may be passed explicitly so the
    The demo can run without a full login UI; production wiring pulls it
    from the panel session (the Cerbos + session bridge).
    """

    if response_type != "code":
        raise HTTPException(400, detail="unsupported_response_type")

    # SECURITY (auth/session round) — identity must be PROVEN, not asserted.
    # The pre-fix MVP read subject/tenant/roles straight from the query string
    # (`user_subject`) or the `x-abs-user-sub` header with no auth dependency,
    # so anyone who could reach a registered client could mint a token for ANY
    # user/role/tenant (full auth-bypass + privilege-escalation the moment a
    # token consumer is wired — deps.get_auth_context already consumes these
    # RS256 tokens). Resolution order:
    #   1. Authenticated panel session → subject + tenant + roles from
    #      server-side state (users table), caller query/header IGNORED.
    #   2. No session, env=prod → refuse (401). Never trust caller identity.
    #   3. No session, non-prod → legacy explicit-subject path for the
    #      login-UI-less demo + the test harness only.
    principal = _session_principal(request)
    if principal is not None:
        subject, final_tenant, final_roles = principal
    elif settings.env == "prod":
        raise HTTPException(401, detail="login_required")
    else:
        subject = user_subject or request.headers.get("x-abs-user-sub", "")
        final_tenant = tenant_id
        final_roles = (
            [r.strip() for r in roles.split(",") if r.strip()] if roles else None
        )
        # Even on the non-prod demo path, a deactivated/revoked user must not
        # mint a token (defense-in-depth parity with the session path).
        from app.api.auth import _subject_revoked

        if subject and _subject_revoked(subject):
            raise HTTPException(401, detail="login_required")

    if not subject:
        raise HTTPException(401, detail="login_required")

    extras: dict[str, object] = {}
    if final_tenant:
        extras["tnt"] = final_tenant
    if final_roles:
        extras["roles"] = final_roles

    try:
        record = issue_authorization_code(
            db,
            client_id=client_id,
            user_subject=subject,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            nonce=nonce,
            extra_claims=extras or None,
        )
    except OAuthError as exc:
        return _err_response(exc)

    # CodeQL — read the redirect_uri back from the issued auth-code
    # record. issue_authorization_code() called _check_redirect() against
    # the OAuthClient's registered allow-list (newline-separated, exact
    # match) before persisting, so `record.redirect_uri` is guaranteed to
    # be one of the client's pre-registered values. Using the form
    # parameter directly here is functionally equivalent but CodeQL's
    # taint model does not track sanitization through the persistence
    # layer; reading from record breaks the taint flow at the data-store
    # boundary.
    validated_redirect_uri = record.redirect_uri
    qs = f"code={record.code}"
    if state:
        qs += f"&state={state}"
    sep = "&" if "?" in validated_redirect_uri else "?"
    return RedirectResponse(url=f"{validated_redirect_uri}{sep}{qs}", status_code=302)


@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: str = Form(...),
    client_secret: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    db: Session = Depends(get_session),
) -> JSONResponse:
    try:
        if grant_type == "authorization_code":
            if not (code and redirect_uri and code_verifier):
                raise OAuthError(
                    "invalid_request",
                    "code, redirect_uri and code_verifier are required",
                )
            payload = exchange_code_for_tokens(
                db,
                client_id=client_id,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
                client_secret=client_secret,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                raise OAuthError("invalid_request", "refresh_token is required")
            payload = refresh_access_token(
                db,
                client_id=client_id,
                refresh_token=refresh_token,
                client_secret=client_secret,
            )
        else:
            raise OAuthError("unsupported_grant_type", grant_type)
    except OAuthError as exc:
        await publish_login_failed(
            client_id=client_id,
            reason=exc.description or exc.code,
            error_code=exc.code,
            metadata={"grant_type": grant_type},
        )
        return _err_response(exc)

    # Successful issue → emit login.success. Subject from JWT claims.
    try:
        import jwt as _jwt

        from app.auth.oauth.jwks import public_verification_key

        claims = _jwt.decode(
            payload["access_token"],
            public_verification_key(),
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False},
        )
        await publish_login_success(
            user_id=str(claims.get("sub", "")),
            client_id=client_id,
            tenant_id=claims.get("tnt"),
            scope=payload.get("scope", ""),
            metadata={"grant_type": grant_type, "jti": claims.get("jti")},
        )
    except Exception as exc:  # noqa: BLE001 — never block token response
        logger.warning("login.success event emit failed: %s", exc)

    return JSONResponse(payload)


@router.get("/.well-known/jwks.json")
async def jwks() -> JSONResponse:
    return JSONResponse(jwks_document())


@router.get("/.well-known/openid-configuration")
async def openid_configuration() -> JSONResponse:
    issuer = getattr(settings, "oauth_issuer", ISSUER)
    return JSONResponse(
        {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "jwks_uri": f"{issuer}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "none",
            ],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )
