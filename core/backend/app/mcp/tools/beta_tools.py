# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""`beta_metrics` MCP tool.

Reports waitlist + conversion + recent-signup signals from `beta_requests` and
`licenses`. Read-only; no live external API.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


def _counts() -> dict:
    from sqlmodel import Session, select

    from app.db.models import BetaRequest, License
    from app.db.session import get_engine

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    out = {
        "pending": 0,
        "approved": 0,
        "rejected": 0,
        "signups_24h": 0,
        "signups_7d": 0,
        "approved_to_paid": 0,
        "approved_total": 0,
        "conversion_rate": None,
    }
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            if r.status in out:
                out[r.status] = out.get(r.status, 0) + 1
            ts = r.created_at
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= last_24h:
                    out["signups_24h"] += 1
                if ts >= last_7d:
                    out["signups_7d"] += 1
            if r.status == "approved":
                out["approved_total"] += 1
                if r.license_jti:
                    lic = db.scalars(
                        select(License).where(License.jti == r.license_jti)
                    ).first()
                    if lic and lic.tier and lic.tier != "beta":
                        out["approved_to_paid"] += 1

    if out["approved_total"]:
        out["conversion_rate"] = round(
            out["approved_to_paid"] / out["approved_total"], 4
        )
    return out


@mcp_server.tool()
@with_hooks("beta_metrics")
async def beta_metrics() -> str:
    """Beta waitlist counts, recent signups, paid-conversion rate."""
    await tracker.bump("beta_metrics")
    return json.dumps(_counts(), indent=2, ensure_ascii=False)


REGISTERED_TOOLS.extend(["beta_metrics"])
