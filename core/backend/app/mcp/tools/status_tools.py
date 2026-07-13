# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""`status_check` MCP tool.

Wraps `/v1/status` shape + last 24h key business metrics:
  - license_count (active / revoked / expired)
  - revenue_today_usd (gross from billing_status)
  - recent_errors (last 5 webhook events with error)
"""

from __future__ import annotations

import json
import time
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


_BOOT_TIME = time.time()


@mcp_server.tool()
@with_hooks("status_check")
async def status_check() -> str:
    """025 — System status + 24h business metrics for solo operator dashboard."""
    await tracker.bump("status_check")
    from datetime import datetime, timezone

    from sqlmodel import select

    from app.db.models import License, WebhookEvent
    from app.db.session import get_session_sync

    out: dict = {
        "uptime_seconds": int(time.time() - _BOOT_TIME),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Reuse status_page service checks
    try:
        from app.api.status_page import (
            _check_db,
            _check_email,
            _check_mcp,
            _check_providers,
            _check_rag,
            _check_stripe,
            _check_vault,
        )

        out["services"] = [
            _check_db(),
            _check_vault(),
            _check_providers(),
            _check_rag(),
            _check_mcp(),
            _check_email(),
            _check_stripe(),
        ]
        fail = sum(1 for s in out["services"] if not s["ok"])
        out["overall"] = "ok" if fail == 0 else ("degraded" if fail <= 2 else "down")
    except Exception as exc:
        out["services"] = []
        out["overall"] = "unknown"
        out["error"] = str(exc)[:200]

    # License counts
    now = datetime.now(timezone.utc)
    with get_session_sync() as db:
        rows = db.scalars(select(License)).all()
        active = revoked = expired = 0
        for lic in rows:
            if lic.revoked_at is not None:
                revoked += 1
                continue
            exp_at = lic.expires_at
            if exp_at.tzinfo is None:
                exp_at = exp_at.replace(tzinfo=timezone.utc)
            if exp_at <= now:
                expired += 1
            else:
                active += 1
        out["licenses"] = {
            "active": active,
            "revoked": revoked,
            "expired": expired,
            "total": len(rows),
        }

        # Revenue today (gross, simple SKU map). Q12-R84: prices from settings.
        from app.config import settings as _s

        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        price_map = {
            ("self-host", 1): _s.abs_seat_price_self_host,
            ("team", 5): _s.abs_seat_price_team_5,
            ("team", 10): _s.abs_seat_price_team_10,
        }
        revenue_today = 0.0
        for lic in rows:
            issued_at = lic.issued_at
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=timezone.utc)
            if issued_at >= today_start:
                revenue_today += price_map.get((lic.tier, lic.seat_count), 0)
        out["revenue_today_usd"] = round(revenue_today, 2)

        # Recent webhook errors
        recent = db.scalars(
            select(WebhookEvent)
            .where(WebhookEvent.error.is_not(None))  # type: ignore[union-attr]
            .order_by(WebhookEvent.received_at.desc())  # type: ignore[union-attr]
            .limit(5)
        ).all()
        out["recent_errors"] = [
            {
                "event_id": r.event_id,
                "event_type": r.event_type,
                "error": r.error,
            }
            for r in recent
        ]

    return json.dumps(out, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["status_check"])
