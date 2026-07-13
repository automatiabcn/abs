# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""013 — Vault rotation + status API (admin auth zorunlu).

POST /v1/secrets/rotate {key, new_value} → write_secret + invalidate cache + audit
GET  /v1/secrets/status                  → vault_enabled + per-key configured (NO CLEARTEXT)
"""

from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.observability.audit import emit_event  # Q12-L24 sweep 3

router = APIRouter(prefix="/v1/secrets", tags=["secrets"])


class RotateRequest(BaseModel):
    key: str = Field(..., min_length=3)
    new_value: str = Field(..., min_length=1)


@router.post("/rotate")
async def rotate_secret(
    body: RotateRequest,
    request: Request,
    _admin: dict = Depends(current_admin),
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
        emit_event(
            request,
            action="secrets.rotate",
            outcome="denied",
            reason="vault_not_configured",
            status_code=503,
            provider="vault",
        )
        raise HTTPException(status_code=503, detail="The vault is not configured")
    if body.key not in known_keys():
        emit_event(
            request,
            action="secrets.rotate",
            outcome="denied",
            reason="unknown_key",
            status_code=400,
            provider="vault",
        )
        raise HTTPException(status_code=400, detail=f"Bilinmeyen key: {body.key}")
    try:
        write_secret(body.key, body.new_value)
    except VaultError as exc:
        # Q12-L24 sweep 3 — pre-fix `f"Vault yazma hatasi: {exc}"`
        # leaked sops/age stderr (file paths, key fingerprints,
        # subprocess details). Generic detail; error_class to audit only.
        emit_event(
            request,
            action="secrets.rotate",
            outcome="error",
            reason="vault_write_failed",
            status_code=500,
            provider="vault",
            error_class=type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="vault_write_failed") from exc
    log_event("rotate", body.key, source="panel_api")
    invalidate()
    emit_event(
        request,
        action="secrets.rotate",
        outcome="success",
        provider="vault",
    )
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
