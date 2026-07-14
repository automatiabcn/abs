# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""License activation and status endpoints."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.licensing import gate as licence_gate
from app.licensing import verify_license

router = APIRouter(prefix="/v1/license", tags=["license"])


class ActivateRequest(BaseModel):
    """Activation request body."""

    license_key: str = Field(..., min_length=10)


def _persist_license_key_to_env(key: str, env_path: str) -> bool:
    """Persist the license key to the .env file.

    Written through a temp file + move so a crash mid-write cannot truncate an
    existing .env. Returns False when the file does not exist; persistence is
    not required in dev/test.
    """
    env_file = Path(env_path)
    if not env_file.is_file():
        return False

    lines = env_file.read_text(encoding="utf-8").splitlines()
    prefix = "ABS_LICENSE_KEY="

    updated = False
    for idx, line in enumerate(lines):
        if line.startswith(prefix):
            lines[idx] = f"{prefix}{key}"
            updated = True
            break

    if not updated:
        lines.append(f"{prefix}{key}")

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        encoding="utf-8",
        dir=str(env_file.parent),
    ) as tmp:
        tmp.write("\n".join(lines) + "\n")
        tmp_path = Path(tmp.name)

    shutil.move(str(tmp_path), str(env_file))
    return True


@router.post("/activate", status_code=status.HTTP_200_OK)
async def activate_license(body: ActivateRequest) -> Dict[str, Any]:
    """Verify a license key, then store it in runtime settings and .env."""
    payload = verify_license(body.license_key)

    settings.license_key = body.license_key

    env_path = settings.model_config.get("env_file", "/app/.env")
    _persist_license_key_to_env(body.license_key, env_path)

    return {
        "status": "activated",
        "tier": payload.get("tier"),
        "seat_count": payload.get("seat_count"),
        "expires_at": datetime.fromtimestamp(
            payload["exp"], tz=timezone.utc
        ).isoformat(),
    }


@router.get("/status", status_code=status.HTTP_200_OK)
async def license_status() -> Dict[str, Any]:
    """Current license status."""
    if not settings.license_key:
        return {"status": "unconfigured"}

    try:
        payload = verify_license(settings.license_key)
    except HTTPException as exc:
        det = str(exc.detail or "").lower()
        # Verify_license reports expiry only through the detail text, so the
        # 401 has to be classified by substring; anything else is "invalid".
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and "expired" in det:
            return {"status": "expired"}
        return {"status": "invalid", "detail": exc.detail}

    # A signature-valid license can still have been revoked after a refund or
    # Chargeback, which only the DB knows about.
    revoked_info = _check_revoked_at(payload.get("jti"))
    if revoked_info is not None:
        return {
            "status": "revoked",
            "jti": payload.get("jti"),
            "revoked_at": revoked_info["revoked_at"],
            "reason": revoked_info["reason"],
        }

    return {
        "status": "active",
        "tier": payload.get("tier"),
        "seat_count": payload.get("seat_count"),
        "customer_id": payload.get("customer_id"),
        "expires_at": datetime.fromtimestamp(
            payload["exp"], tz=timezone.utc
        ).isoformat(),
        "jti": payload.get("jti"),
    }


def _check_revoked_at(jti: str | None) -> dict | None:
    """Returns reason + date when the License row has revoked_at set, else None.

    Any DB failure is swallowed: a license that verifies cryptographically must
    not be rejected because the revocation lookup broke.
    """
    if not jti:
        return None
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            row = db.scalars(select(License).where(License.jti == jti)).first()
            if row is None or row.revoked_at is None:
                return None
            revoked_at = row.revoked_at
            if revoked_at.tzinfo is None:
                revoked_at = revoked_at.replace(tzinfo=timezone.utc)
            return {
                "revoked_at": revoked_at.isoformat(),
                "reason": row.revoked_reason or "unknown",
            }
    except Exception:
        return None


@router.get("/demo-status", status_code=status.HTTP_200_OK)
async def demo_status_endpoint() -> Dict[str, Any]:
    """Demo countdown state. Polled by the UI banner."""
    from app.licensing.demo import status as demo_status

    return demo_status()


def _unverified_claims() -> Dict[str, Any]:
    """The licence's own claims, read without checking the signature.

    Only ever used to *describe* a key the gate has already judged — a tier or
    an expiry date on a settings page, never a decision. Decisions come from
    `licence_gate.evaluate()`, which does check the signature.
    """
    import jwt as pyjwt

    try:
        return dict(
            pyjwt.decode(settings.license_key, options={"verify_signature": False})
        )
    except Exception:
        return {}


@router.get("/info", status_code=status.HTTP_200_OK)
async def license_info() -> Dict[str, Any]:
    """Single source of truth for the Settings → License tab.

    The verdict here is the same one the chat gate enforces —
    `licence_gate.evaluate()`. It used to be computed separately, and the two
    disagreed: the gate watched the activation cache for revocations while this
    endpoint read `License.revoked_at` from the database, and neither knew about
    the other's grace window. A settings page that says "licensed" while chat
    answers 403 is worse than no settings page.

    `allowed` is the honest headline: can this install actually be used right
    now. `status` says why.
    """
    from app.licensing.demo import status as demo_status

    empty = {
        "tier": None,
        "jti": None,
        "seat_count": None,
        "expires_at": None,
        "customer_id": None,
        "demo": None,
    }

    decision = licence_gate.evaluate()

    # The trial, running or over. Both branches have to be here: while the
    # verdicts were unhandled they fell through to the licensed branch below,
    # and a server whose trial had expired described itself to its owner as
    # "licensed" — with every licence field null — while chat answered 403.
    if decision.verdict is licence_gate.Verdict.TRIAL:
        return {**empty, "status": "trial", "allowed": True, "demo": demo_status()}

    if decision.verdict is licence_gate.Verdict.TRIAL_EXPIRED:
        return {
            **empty,
            "status": "trial_expired",
            "allowed": False,
            "demo": demo_status(),
            "detail": decision.detail,
            "reason": decision.reason,
        }

    if decision.verdict is licence_gate.Verdict.UNLICENSED:
        return {**empty, "status": "trial", "allowed": True, "demo": demo_status()}

    if decision.verdict is licence_gate.Verdict.INVALID:
        return {
            **empty,
            "status": "invalid",
            "allowed": False,
            "detail": decision.reason,
        }

    claims = _unverified_claims()
    described = {
        "tier": claims.get("tier"),
        "jti": claims.get("jti"),
        "seat_count": claims.get("seat_count"),
        "expires_at": (
            datetime.fromtimestamp(claims["exp"], tz=timezone.utc).isoformat()
            if claims.get("exp")
            else None
        ),
        "customer_id": claims.get("customer_id"),
        "demo": None,
    }

    if decision.verdict is licence_gate.Verdict.REVOKED:
        revoked_info = _check_revoked_at(claims.get("jti")) or {}
        return {
            **described,
            "status": "revoked",
            "allowed": False,
            "reason": decision.reason,
            "revoked_at": revoked_info.get("revoked_at"),
        }

    if decision.verdict is licence_gate.Verdict.EXPIRED:
        return {**described, "status": "expired", "allowed": False}

    if decision.verdict is licence_gate.Verdict.IN_GRACE:
        # Expired, still working, and the operator has a week to notice. Saying
        # "licensed" here would be the kind of comfortable lie that turns into a
        # surprise outage on day eight.
        return {
            **described,
            "status": "in_grace",
            "allowed": True,
            "grace_days": licence_gate.GRACE_DAYS,
        }

    return {**described, "status": "licensed", "allowed": True}
