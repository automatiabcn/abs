# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 4 / Q2.CO1 — UsageLog service: append + aggregate.

Sister of `feature_usage` but tracks **provider tokens/cost** (not feature
hits). Cascade provider calls call `append()`; quota_monitor reads
`monthly_sum()`.

Like `feature_usage`, write failures are swallowed at debug level so
business flows never break on telemetry hiccups.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlmodel import Session, func, select

from app.db.models import UsageLog
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def append(
    provider: str,
    tokens: int,
    *,
    tenant_slug: str = "default",
    cost_usd: float = 0.0,
    request_id: Optional[str] = None,
) -> None:
    if tokens < 0 or cost_usd < 0 or not provider:
        # negative tokens/cost would corrupt the metering aggregate that
        # quota gating reads — drop the row rather than let it through.
        return
    row = UsageLog(
        provider=provider,
        tenant_slug=tenant_slug,
        tokens=int(tokens),
        cost_usd=float(cost_usd),
        request_id=request_id,
        ts=datetime.now(timezone.utc),
    )
    try:
        with Session(get_engine()) as db:
            db.add(row)
            db.commit()
    except Exception as exc:
        logger.debug("usage_log append failed: %s", exc)


def monthly_sum(
    provider: str, start: datetime, end: datetime, tenant_slug: Optional[str] = None
) -> Tuple[int, float]:
    """Return (token_total, cost_total) for the window."""
    try:
        with Session(get_engine()) as db:
            stmt = select(
                func.coalesce(func.sum(UsageLog.tokens), 0),
                func.coalesce(func.sum(UsageLog.cost_usd), 0.0),
            ).where(
                UsageLog.provider == provider,
                UsageLog.ts >= start,
                UsageLog.ts <= end,
            )
            if tenant_slug is not None:
                stmt = stmt.where(UsageLog.tenant_slug == tenant_slug)
            row = db.execute(stmt).one_or_none()
            if not row:
                return 0, 0.0
            tokens, cost = row
            return int(tokens or 0), float(cost or 0.0)
    except Exception as exc:
        logger.debug("usage_log monthly_sum failed: %s", exc)
        return 0, 0.0


def reset_for_tests() -> None:
    try:
        with Session(get_engine()) as db:
            db.execute(UsageLog.__table__.delete())
            db.commit()
    except Exception as exc:
        logger.debug("usage_log reset failed: %s", exc)


__all__ = ["append", "monthly_sum", "reset_for_tests"]
