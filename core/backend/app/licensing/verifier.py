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


# Grace window: past expires_at the license stays read-only for GRACE_DAYS,
# after which it is hard-rejected.
GRACE_DAYS = 7


class LicenseStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED_PENDING_GRACE = "expired_pending_grace"
    EXPIRED = "expired"


def verify_license(token: str) -> dict:
    """Verify a license JWT (RS256) against the configured public key.

    Raises:
        HTTPException 401 — expired or bad signature.
        HTTPException 400 — malformed token or any other JWT error.

    The generic 400 detail is deliberate: echoing the JWT library's exception
    text back to a client leaks decoder internals. The exception class is
    logged instead, for operators only.
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

    # Hardware binding. Licenses minted without `machine_fp` stay valid on any
    # host — the check only applies when the claim is present.
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
    """Compare the License row's ``expires_at`` against the wall clock.

    The JWT's own ``exp`` is not the whole story: a license can be expired and
    still usable read-only inside the grace window.

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
