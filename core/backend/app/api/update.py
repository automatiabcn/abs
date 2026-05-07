# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""014 — Update channel endpoints (check/changelog/apply/pending)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_admin
from app.update.applier import clear_pending, pending_status, trigger_pull
from app.update.manifest import fetch_manifest, update_state

router = APIRouter(prefix="/v1/update", tags=["update"])


def _current_version() -> str:
    """app.version'i lazy import — circular önler."""
    from app.main import app as fastapi_app

    return fastapi_app.version


@router.get("/check")
async def check_update():
    """Public — kullanıcı kontrol edebilir, ama apply admin auth ister."""
    manifest = await fetch_manifest()
    return update_state(manifest, _current_version())


@router.get("/changelog")
async def changelog(_admin: dict = Depends(current_admin)):
    """CJ-012 — manifest yoksa/registry erisilemiyorsa 503 yerine bos changelog
    dondur. Self-host kurulumlarinda upstream registry opsiyonel."""
    manifest = await fetch_manifest()
    if "error" in manifest:
        return {
            "changelog_url": None,
            "summary": "",
            "released_at": None,
            "version": _current_version(),
            "entries": [],
            "note": f"upstream_unavailable: {manifest['error']}",
        }
    return {
        "changelog_url": manifest.get("changelog_url"),
        "summary": manifest.get("changelog_summary"),
        "released_at": manifest.get("released_at"),
        "version": manifest.get("current_version"),
        "entries": manifest.get("entries", []),
    }


@router.post("/apply")
async def apply_update(_admin: dict = Depends(current_admin)):
    payload = await trigger_pull()
    return {"status": "ok", "pending": payload}


@router.get("/pending")
async def get_pending(_admin: dict = Depends(current_admin)):
    return pending_status()


@router.delete("/pending")
async def clear_pending_endpoint(_admin: dict = Depends(current_admin)):
    return {"cleared": clear_pending()}
