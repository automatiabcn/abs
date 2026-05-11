# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""032 Modul B — Aggregated admin dashboard.

GET /v1/admin/dashboard

Pulls 5 sources (billing/security/compliance/beta/vault) and returns a
single payload. Disk-backed 5-min cache so repeated polling stays cheap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)

CACHE_PATH = Path("/tmp/abs_admin_dashboard_cache.json")
CACHE_TTL_SECONDS = 5 * 60

# Sprint 2D ITEM-2.2 — CodeQL py/clear-text-storage-sensitive-data (#32).
# The aggregated dashboard payload may transitively contain provider keys,
# webhook secrets, or audit-chain HMACs. Mask any field whose key (or value
# prefix) suggests a secret before persisting to the on-disk cache.
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|webhook|signing[_-]?key|"
    r"private[_-]?key|access[_-]?key|client[_-]?secret|bearer)"
)
_SENSITIVE_VALUE_PREFIXES = (
    "sk-",
    "ghp_",
    "ghs_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "AIza",
    "Bearer ",
)


def _mask_value(v: Any) -> Any:
    if isinstance(v, str) and v:
        if len(v) <= 8:
            return "***"
        return f"{v[:3]}***{v[-2:]}"
    return "***"


def _sanitize_for_cache(value: Any) -> Any:
    """Recursively strip/mask values that look like secrets before disk write."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_KEY_RE.search(k):
                out[k] = _mask_value(v)
            else:
                out[k] = _sanitize_for_cache(v)
        return out
    if isinstance(value, list):
        return [_sanitize_for_cache(item) for item in value]
    if isinstance(value, str):
        for prefix in _SENSITIVE_VALUE_PREFIXES:
            if value.startswith(prefix):
                return _mask_value(value)
    return value


def _read_cache() -> dict | None:
    try:
        if not CACHE_PATH.exists():
            return None
        data = json.loads(CACHE_PATH.read_text())
        if time.time() - float(data.get("_ts", 0)) < CACHE_TTL_SECONDS:
            return data
    except Exception:
        return None
    return None


def _write_cache(payload: dict) -> None:
    try:
        sanitized = _sanitize_for_cache(payload)
        body = dict(sanitized) if isinstance(sanitized, dict) else {"payload": sanitized}
        body["_ts"] = time.time()
        # Sprint 2D ITEM-2.2 — write with 0600 perms (owner read/write only).
        # Defense-in-depth on top of the sanitizer.
        serialized = json.dumps(body, default=str)
        fd = os.open(str(CACHE_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, serialized.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:
        logger.debug("dashboard cache write failed: %s", exc)


def reset_cache_for_tests() -> None:
    try:
        if CACHE_PATH.exists():
            CACHE_PATH.unlink()
    except Exception:
        pass


async def _safe(coro_factory, default: Any) -> Any:
    """Run a tool-call, swallow any failure to return `default`."""
    try:
        result = coro_factory()
        if asyncio.iscoroutine(result):
            return await result
        return result
    except Exception as exc:
        logger.info("dashboard source failed (%s): %s", default, exc)
        return default


def _parse_json_or_default(raw: str | dict, default: dict) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


async def _build_dashboard() -> dict:
    from app.mcp.tools.beta_tools import beta_metrics
    from app.mcp.tools.compliance_tools import compliance_status
    from app.mcp.tools.security_tools import security_audit
    from app.mcp.tools.vault_audit_tools import vault_audit_status

    # Run independent sources in parallel
    results = await asyncio.gather(
        _safe(beta_metrics, "{}"),
        _safe(compliance_status, "{}"),
        _safe(security_audit, "{}"),
        _safe(vault_audit_status, "{}"),
        return_exceptions=False,
    )
    beta_raw, compliance_raw, security_raw, vault_raw = results

    payload = {
        "billing": _billing_summary(),
        "beta": _parse_json_or_default(beta_raw, {}),
        "compliance": _parse_json_or_default(compliance_raw, {}),
        "security": _parse_json_or_default(security_raw, {}),
        "vault": _parse_json_or_default(vault_raw, {}),
        "generated_at": time.time(),
    }
    return payload


def _billing_summary() -> dict:
    """Lightweight billing snapshot: license counts + tier breakdown.

    NOT a Stripe live call. Pulls from local License rows so we avoid
    hitting the live API in dashboard polling.
    """
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            rows = list(db.scalars(select(License)).all())
        active = [
            r
            for r in rows
            if r.revoked_at is None and r.purged_at is None
        ]
        breakdown: dict[str, int] = {}
        for r in active:
            breakdown[r.tier or "unknown"] = breakdown.get(r.tier or "unknown", 0) + 1
        return {
            "licenses_total": len(rows),
            "licenses_active": len(active),
            "tier_breakdown": breakdown,
        }
    except Exception as exc:
        logger.info("billing summary failed: %s", exc)
        return {}


@router.get("/dashboard")
async def dashboard(
    refresh: bool = False,
    _admin: dict = Depends(admin_required),
) -> dict:
    if not refresh:
        cached = _read_cache()
        if cached is not None:
            cached["cached"] = True
            return cached
    body = await _build_dashboard()
    _write_cache(body)
    body["cached"] = False
    return body
