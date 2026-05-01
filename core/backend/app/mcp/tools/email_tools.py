"""019 — Email queue MCP tool: kuyruk durumu + breakdown.

Solo operatör için günlük email durumu kontrolü:
  - by_status: sent / pending / failed
  - by_kind: welcome / walkthrough / first_success / expiry_warning / recovery
  - recent: son N kayıt (kind, scheduled_at, sent_at, attempts, error)
"""

from __future__ import annotations

import json
from typing import List

# REGISTERED_TOOLS must be defined BEFORE app.mcp.server import
REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


@mcp_server.tool()
@with_hooks("email_queue_status")
async def email_queue_status(limit: int = 50) -> str:
    """ABS onboarding email kuyruk dashboard."""
    await tracker.bump("email_queue_status")
    from datetime import datetime, timezone

    from sqlmodel import select

    from app.db.models import EmailQueue
    from app.db.session import get_session_sync

    with get_session_sync() as db:
        rows = db.scalars(
            select(EmailQueue)
            .order_by(EmailQueue.scheduled_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        ).all()

    by_status = {"sent": 0, "pending": 0, "failed": 0}
    by_kind: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    recent: list[dict] = []

    for r in rows:
        if r.sent_at is not None:
            by_status["sent"] += 1
        elif r.attempts >= 3:
            by_status["failed"] += 1
        else:
            by_status["pending"] += 1

        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1

        scheduled_at = r.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        sent_at_iso = None
        if r.sent_at is not None:
            sa = r.sent_at
            if sa.tzinfo is None:
                sa = sa.replace(tzinfo=timezone.utc)
            sent_at_iso = sa.isoformat()
        recent.append(
            {
                "id": r.id,
                "license_jti": r.license_jti,
                "kind": r.kind,
                "scheduled_at": scheduled_at.isoformat(),
                "sent_at": sent_at_iso,
                "attempts": r.attempts,
                "error": r.error,
                "unsubscribed": r.unsubscribed,
            }
        )

    return json.dumps(
        {
            "now": now.isoformat(),
            "total": len(rows),
            "by_status": by_status,
            "by_kind": by_kind,
            "recent": recent,
        },
        ensure_ascii=False,
        indent=2,
    )


REGISTERED_TOOLS.extend(["email_queue_status"])
