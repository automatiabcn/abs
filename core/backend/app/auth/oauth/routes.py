"""T-003 — OAuth 2.1 endpoints (FastAPI router).

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
    Sprint 1 demo can run without a full login UI; production wiring
    pulls it from the panel session (T-038 Cerbos+session bridge).
    """

    if response_type != "code":
        raise HTTPException(400, detail="unsupported_response_type")

    subject = user_subject or request.headers.get("x-abs-user-sub", "")
    if not subject:
        raise HTTPException(401, detail="login_required")

    extras: dict[str, object] = {}
    if tenant_id:
        extras["tnt"] = tenant_id
    if roles:
        extras["roles"] = [r.strip() for r in roles.split(",") if r.strip()]

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

    qs = f"code={record.code}"
    if state:
        qs += f"&state={state}"
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{sep}{qs}", status_code=302)


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
