# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

import enum
import logging
from datetime import datetime, timedelta, timezone

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


# Sprint 2I UAT-027 — beta-license grace window. After expires_at the
# JTI is read-only for ``GRACE_DAYS``; later the license is hard-rejected.
GRACE_DAYS = 7


class LicenseStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED_PENDING_GRACE = "expired_pending_grace"
    EXPIRED = "expired"


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


def license_grace_status(payload: dict) -> LicenseStatus:
    """Sprint 2I UAT-027 — compare License row's ``expires_at`` against
    the live wall clock so the beta lifecycle has a real grace window.

    Returns:
        ACTIVE — License row missing OR expires_at in the future.
        EXPIRED_PENDING_GRACE — expired but within GRACE_DAYS (read-only).
        EXPIRED — past the grace window (caller should deny).
    """
    jti = payload.get("jti")
    if not jti:
        return LicenseStatus.ACTIVE

    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            row = db.scalars(select(License).where(License.jti == jti)).first()
    except Exception as exc:  # pragma: no cover — DB not ready
        logger.debug("license_grace_db_lookup_skip: %s", exc)
        return LicenseStatus.ACTIVE

    if row is None or row.expires_at is None:
        return LicenseStatus.ACTIVE

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at > now:
        return LicenseStatus.ACTIVE
    if now - expires_at <= timedelta(days=GRACE_DAYS):
        return LicenseStatus.EXPIRED_PENDING_GRACE
    return LicenseStatus.EXPIRED


def verify_license_with_grace(token: str) -> tuple[dict, LicenseStatus]:
    """Verify the JWT and report grace-window status in one shot.

    Hard-rejects (``HTTPException`` 401) when the license is past the
    grace window so caller routes don't need to repeat the check.
    """
    payload = verify_license(token)
    status_ = license_grace_status(payload)
    if status_ is LicenseStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="license_expired_grace_elapsed",
        )
    return payload, status_
