from __future__ import annotations

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


def verify_license(token: str) -> dict:
    """JWT lisans token'ını RS256 + public key ile doğrular.

    Hata durumları:
        - 401: Süresi dolmuş ya da imza geçersiz
        - 400: Format bozuk ya da diğer JWT hataları
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"License verification error: {exc}",
        ) from exc
