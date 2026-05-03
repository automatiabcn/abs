from __future__ import annotations

import logging

import jwt
from fastapi import HTTPException, status
from jwt import (
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWTError,
)

from app.config import settings

from .keys import load_public_key

logger = logging.getLogger(__name__)


def verify_license(token: str) -> dict:
    """JWT lisans token'ını RS256 + public key ile doğrular.

    Hata durumları:
        - 401: Süresi dolmuş ya da imza geçersiz
        - 400: Format bozuk ya da diğer JWT hataları

    Q12-L24-007 (LOW security info-leak) — the catch-all PyJWTError
    branch previously responded with `f"License verification error:
    {exc}"`, exposing PyJWT internals (constraint names, decoder state)
    to clients. Sibling leaks (admin/me_*/secrets/vault) were closed in
    R14/R18/R19/R22/R25; this branch was the last one. Generic detail +
    `error_class` taxonomy logged for ops audit only.
    """

    public_key_bytes = load_public_key(settings.public_key_path)

    try:
        return jwt.decode(
            token,
            key=public_key_bytes,
            algorithms=["RS256"],
            options={"require": ["exp", "iat", "jti"]},
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="License has expired",
        ) from exc
    except InvalidSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="License signature invalid",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License format invalid",
        ) from exc
    except PyJWTError as exc:
        logger.warning(
            "license_verify_pyjwt_error error_class=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="license_verify_failed",
        ) from exc
