# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Remote release manifest fetch + cache + version compare."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL = 6 * 3600  # 6 saat


def _cache_path() -> Path:
    p = Path(settings.data_dir) / "update_cache.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def _read_cache() -> Optional[Dict[str, Any]]:
    p = _cache_path()
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - d.get("fetched_at", 0) > CACHE_TTL:
            return None
        manifest = d.get("manifest")
        return manifest if isinstance(manifest, dict) else None
    except Exception:
        return None


def _write_cache(manifest: Dict[str, Any]) -> None:
    p = _cache_path()
    payload = {"fetched_at": time.time(), "manifest": manifest}
    try:
        p.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


async def fetch_manifest(force: bool = False) -> Dict[str, Any]:
    """Cache-aware manifest fetch + 015 RS256 signature verify (fail-closed)."""
    if not force:
        cached = _read_cache()
        if cached:
            return cached
    url = settings.update_manifest_url
    if not url:
        return {"error": "update_manifest_url is not configured"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        if r.status_code >= 400:
            return {"error": f"manifest fetch {r.status_code}"}
        manifest_bytes = r.content
        manifest = r.json()
        if not isinstance(manifest, dict):
            return {"error": "manifest must be a JSON object"}
    except Exception:
        # CodeQL py/stack-trace-exposure (#12/#13). The
        # caller (api/update.py) embeds this `error` field in HTTP responses;
        # do not leak raw exception text. Log full detail server-side, return
        # only an opaque correlation id.
        import uuid as _uuid

        request_id = _uuid.uuid4().hex[:12]
        logger.exception("manifest_fetch_failed request_id=%s", request_id)
        return {"error": "manifest_fetch_failed", "request_id": request_id}

    # Fail-closed signature verify (settings.update_signature_required)
    if settings.update_signature_required:
        from app.update.signature import fetch_signature, verify_manifest

        sig = await fetch_signature(url)
        if not sig:
            return {"error": "signature missing — refused (fail-closed)"}
        if not verify_manifest(manifest_bytes, sig):
            return {"error": "signature invalid — refused (fail-closed)"}

    _write_cache(manifest)
    return manifest


def compare_versions(current: str, latest: str) -> int:
    """Semver-lite compare: -1 current<latest, 0 equal, 1 current>latest. 0 on any parse error."""

    def _parse(v: str) -> tuple:
        return tuple(int(x) for x in v.split(".")[:3])

    try:
        a, b = _parse(current), _parse(latest)
        return (a > b) - (a < b)
    except Exception:
        return 0


def update_state(manifest: Dict[str, Any], current_version: str) -> Dict[str, Any]:
    """Manifest + current → state (current | available | critical | unknown)."""
    if "error" in manifest:
        return {
            "state": "unknown",
            "error": manifest["error"],
            "current": current_version,
        }
    latest = manifest.get("current_version", current_version)
    cmp = compare_versions(current_version, latest)
    if cmp >= 0:
        state = "current"
    else:
        state = "critical" if manifest.get("critical") else "available"
    return {
        "state": state,
        "current": current_version,
        "latest": latest,
        "released_at": manifest.get("released_at"),
        "changelog_url": manifest.get("changelog_url"),
        "changelog_summary": manifest.get("changelog_summary"),
        "critical": manifest.get("critical", False),
        "breaking": manifest.get("breaking", False),
    }
