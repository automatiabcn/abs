"""013 — Vault rotation + status API (admin auth zorunlu).

POST /v1/secrets/rotate {key, new_value} → write_secret + invalidate cache + audit
GET  /v1/secrets/status                  → vault_enabled + per-key configured (NO CLEARTEXT)
"""

from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_admin

router = APIRouter(prefix="/v1/secrets", tags=["secrets"])


class RotateRequest(BaseModel):
    key: str = Field(..., min_length=3)
    new_value: str = Field(..., min_length=1)


@router.post("/rotate")
async def rotate_secret(
    body: RotateRequest, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    from app.vault.audit import log_event
    from app.vault.cache import invalidate, known_keys
    from app.vault.runner import (
        VaultError,
        master_key_exists,
        sops_available,
        write_secret,
    )

    if not sops_available() or not master_key_exists():
        raise HTTPException(status_code=503, detail="Vault yapilandirilmadi")
    if body.key not in known_keys():
        raise HTTPException(status_code=400, detail=f"Bilinmeyen key: {body.key}")
    try:
        write_secret(body.key, body.new_value)
    except VaultError as exc:
        raise HTTPException(status_code=500, detail=f"Vault yazma hatasi: {exc}") from exc
    log_event("rotate", body.key, source="panel_api")
    invalidate()
    return {"status": "ok", "key": body.key, "rotated_at": time.time()}


@router.get("/status")
async def secrets_status(_admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    """Cleartext yok — sadece configured/not-configured listesi + binary durumu."""
    from app.vault.cache import is_loaded, known_keys
    from app.vault.runner import master_key_exists, sops_available

    return {
        "vault_enabled": sops_available() and master_key_exists(),
        "binary_sops": sops_available(),
        "master_key_present": master_key_exists(),
        "keys": [{"name": k, "configured": is_loaded(k)} for k in known_keys()],
    }
