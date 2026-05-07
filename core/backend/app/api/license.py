"""Lisans aktivasyon ve durum sorgulama endpoint'leri."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.licensing import verify_license

router = APIRouter(prefix="/v1/license", tags=["license"])


class ActivateRequest(BaseModel):
    """Aktivasyon isteği gövdesi."""

    license_key: str = Field(..., min_length=10)


def _persist_license_key_to_env(key: str, env_path: str) -> bool:
    """Lisans anahtarını .env dosyasına kalıcı olarak yazar.

    Dosya yoksa False döner (test/dev ortamında persist zorunlu değil).
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
    """Lisans anahtarını doğrular, runtime ve .env'e kaydeder."""
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
    """Mevcut lisansın durumunu döndürür."""
    if not settings.license_key:
        return {"status": "unconfigured"}

    try:
        payload = verify_license(settings.license_key)
    except HTTPException as exc:
        det = str(exc.detail or "").lower()
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and (
            "süresi dolmuş" in det or "expired" in det or "expirado" in det
        ):
            return {"status": "expired"}
        return {"status": "invalid", "detail": exc.detail}

    # 022 — DB'de revoked_at kontrolü (refund/chargeback sonrası)
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
    """022 — License DB'de revoked_at NOT NULL ise reason+date döner."""
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
    """011 — Demo countdown durumu. UI banner'ı bu endpoint'i poll'lar."""
    from app.licensing.demo import status as demo_status

    return demo_status()


@router.get("/info", status_code=status.HTTP_200_OK)
async def license_info() -> Dict[str, Any]:
    """Polish round R6 — single source of truth for the Settings → Lisans tab.

    Combines ``/status`` and ``/demo-status`` into one shape so the frontend
    no longer hardcodes the tier / jti / expires_at trio. Returns ``demo``
    payload when no key is configured so the UI can render the countdown
    inline instead of issuing a second request.
    """
    from app.licensing.demo import status as demo_status

    if not settings.license_key:
        return {
            "status": "demo",
            "tier": None,
            "jti": None,
            "seat_count": None,
            "expires_at": None,
            "customer_id": None,
            "demo": demo_status(),
        }

    try:
        payload = verify_license(settings.license_key)
    except HTTPException as exc:
        det = str(exc.detail or "").lower()
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and (
            "süresi dolmuş" in det or "expired" in det or "expirado" in det
        ):
            return {
                "status": "expired",
                "tier": None,
                "jti": None,
                "seat_count": None,
                "expires_at": None,
                "customer_id": None,
                "demo": None,
            }
        return {
            "status": "invalid",
            "tier": None,
            "jti": None,
            "seat_count": None,
            "expires_at": None,
            "customer_id": None,
            "demo": None,
            "detail": exc.detail,
        }

    revoked_info = _check_revoked_at(payload.get("jti"))
    if revoked_info is not None:
        return {
            "status": "revoked",
            "tier": payload.get("tier"),
            "jti": payload.get("jti"),
            "seat_count": payload.get("seat_count"),
            "expires_at": datetime.fromtimestamp(
                payload["exp"], tz=timezone.utc
            ).isoformat(),
            "customer_id": payload.get("customer_id"),
            "demo": None,
            "revoked_at": revoked_info["revoked_at"],
            "reason": revoked_info["reason"],
        }

    return {
        "status": "licensed",
        "tier": payload.get("tier"),
        "jti": payload.get("jti"),
        "seat_count": payload.get("seat_count"),
        "expires_at": datetime.fromtimestamp(
            payload["exp"], tz=timezone.utc
        ).isoformat(),
        "customer_id": payload.get("customer_id"),
        "demo": None,
    }
