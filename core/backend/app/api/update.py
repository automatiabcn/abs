# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Update channel endpoints (check/changelog/apply/pending)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import current_admin
from app.update.applier import clear_pending, pending_status, trigger_pull
from app.update.manifest import fetch_manifest, update_state

router = APIRouter(prefix="/v1/update", tags=["update"])


def _current_version() -> str:
    """Imported lazily: app.main imports this router, so a module-level import
    would be circular."""
    from app.main import app as fastapi_app

    return fastapi_app.version


@router.get("/check")
async def check_update():
    """Public: anyone may check for an update. Applying one requires admin auth."""
    manifest = await fetch_manifest()
    return update_state(manifest, _current_version())


_SAFE_ERROR_CODES = {
    "manifest_fetch_failed",
    "update_manifest_url is not configured",
    "manifest must be a JSON object",
    "signature missing — refused (fail-closed)",
    "signature invalid — refused (fail-closed)",
}


def _safe_error_label(raw: str | None) -> str:
    """Never echo raw exception text to clients.

    Only allow a fixed allowlist of error codes through. Status-code style
    strings ("manifest fetch 502") are reduced to a generic upstream label.
    """
    if not raw:
        return "upstream_unavailable"
    if raw in _SAFE_ERROR_CODES:
        return raw
    if raw.startswith("manifest fetch "):
        return "upstream_http_error"
    return "upstream_unavailable"


@router.get("/changelog")
async def changelog(_admin: dict = Depends(current_admin)):
    """Returns an empty changelog rather than 503 when the manifest or registry
    is unreachable: the upstream registry is optional for self-hosted installs."""
    manifest = await fetch_manifest()
    if "error" in manifest:
        return {
            "changelog_url": None,
            "summary": "",
            "released_at": None,
            "version": _current_version(),
            "entries": [],
            "note": _safe_error_label(manifest.get("error")),
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
