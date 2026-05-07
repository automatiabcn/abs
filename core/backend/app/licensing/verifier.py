# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

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

from .fingerprint import collect_machine_fingerprint
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
        payload = jwt.decode(
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

    # Q12 IP-Hardening R1 — hardware fingerprint binding.
    # Backwards compat: legacy licenses without `machine_fp` stay valid.
    bound_fp = payload.get("machine_fp")
    if bound_fp:
        try:
            live_fp = collect_machine_fingerprint()
        except Exception:  # pragma: no cover — degraded host (no FP components)
            logger.warning("license_machine_fp_collect_failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="license_machine_mismatch",
            )
        if live_fp != bound_fp:
            logger.warning(
                "license_machine_fp_mismatch jti=%s",
                payload.get("jti"),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="license_machine_mismatch",
            )

    return payload
