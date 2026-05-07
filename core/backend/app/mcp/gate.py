# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""011 — MCP tool cagrilarinda lisans/demo enforcement gate.

Public API:
  - `_gate_status() -> dict` — anlik durum (license_active, demo_active, allowed)
  - `with_gate(tool_name) -> decorator` — opsiyonel tek-tool wrapper

Mevcut `with_hooks` decorator'i `_gate_status()` cagirir;
`mcp_require_license=True` oldugunda allowed=False ise tool calistirilmaz —
`[LISANS GEREKLI]` mesaji doner.
"""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


_BLOCK_MESSAGE = (
    "[LICENSE REQUIRED] ABS currently requires a license. "
    "Demo period ended or license not configured. "
    "Buy: https://abs.automatiabcn.com/"
)


def _verify_license_payload() -> Optional[Dict[str, Any]]:
    """Gecerli license payload'unu dondur, hata veya yoksa None."""
    if not settings.license_key:
        return None
    try:
        from app.licensing import verify_license

        payload = verify_license(settings.license_key)
        exp = payload.get("exp", 0)
        if exp <= time.time():
            return None
        return payload
    except Exception:
        return None


def _license_revoked_in_db(jti: Optional[str]) -> bool:
    """JWT gecerli ama DB'de revoke edilmis mi? (refund flow)"""
    if not jti:
        return False
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            from app.db.query_helpers import first_or_none

            row = first_or_none(db, select(License).where(License.jti == jti))
            if row and row.revoked_at is not None:
                return True
    except Exception as exc:
        logger.info("gate revoke check skipped: %s", exc)
    return False


def _gate_status() -> Dict[str, Any]:
    """Anlik gate durumu — license_active, demo_active, allowed."""
    payload = _verify_license_payload()
    license_active = payload is not None
    if license_active:
        if _license_revoked_in_db((payload or {}).get("jti")):
            license_active = False

    demo_active = False
    try:
        from app.licensing.demo import is_active as demo_is_active

        demo_active = demo_is_active()
    except Exception:
        demo_active = False

    allowed = (not settings.mcp_require_license) or license_active or demo_active
    return {
        "license_active": license_active,
        "demo_active": demo_active,
        "allowed": allowed,
        "require_license": settings.mcp_require_license,
    }


def with_gate(tool_name: str) -> Callable:
    """Opsiyonel — tek-tool gate sarmalayici (with_hooks zaten icinde cagiriyor)."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            s = _gate_status()
            if not s["allowed"]:
                return _BLOCK_MESSAGE
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
