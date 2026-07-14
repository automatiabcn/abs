"""email_queue_status MCP tool: response shape + breakdown."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.db.models import EmailQueue
from app.db.session import get_engine


def _seed_queue(jti: str = "jti_q_status"):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(
            EmailQueue(
                license_jti=jti,
                customer_email="qstat@x.co",
                kind="welcome",
                scheduled_at=now - timedelta(hours=2),
                sent_at=now - timedelta(hours=1),
            )
        )
        s.add(
            EmailQueue(
                license_jti=jti,
                customer_email="qstat@x.co",
                kind="walkthrough",
                scheduled_at=now + timedelta(hours=2),
            )
        )
        s.add(
            EmailQueue(
                license_jti=jti,
                customer_email="qstat@x.co",
                kind="recovery",
                scheduled_at=now - timedelta(days=3),
                attempts=3,
                error="SMTP timeout",
            )
        )
        s.commit()


def test_email_queue_status_response_shape():
    _seed_queue("jti_q_shape")
    from app.mcp.tools.email_tools import email_queue_status

    raw = asyncio.run(email_queue_status(limit=50))
    out = json.loads(raw)
    assert "by_status" in out
    assert "by_kind" in out
    assert "recent" in out
    assert "now" in out
    assert isinstance(out["recent"], list)


def test_email_queue_status_breakdown_sums():
    _seed_queue("jti_q_break")
    from app.mcp.tools.email_tools import email_queue_status

    raw = asyncio.run(email_queue_status(limit=50))
    out = json.loads(raw)
    # by_status counts → at least we have our seeded ones
    assert out["by_status"]["sent"] >= 1
    assert out["by_status"]["pending"] >= 1
    assert out["by_status"]["failed"] >= 1
    # by_kind includes welcome, walkthrough, recovery
    for kind in ("welcome", "walkthrough", "recovery"):
        assert out["by_kind"].get(kind, 0) >= 1
