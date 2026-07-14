"""`compliance_status` MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_compliance_status_response_shape():
    from app.mcp.tools.compliance_tools import compliance_status

    raw = asyncio.run(compliance_status())
    out = json.loads(raw)
    for key in (
        "audit_log",
        "data_export_jobs",
        "deletions",
        "consents",
        "docs",
        "overall_status",
    ):
        assert key in out, f"missing key: {key}"
    assert out["overall_status"] in {"ok", "warn", "gap"}


def test_compliance_status_reflects_pending_deletions():
    from datetime import datetime, timedelta, timezone

    from sqlmodel import Session, select

    from app.db.models import License
    from app.db.session import get_engine
    from app.licensing import generate_license
    from app.mcp.tools.compliance_tools import compliance_status

    import jwt as pyjwt

    token = generate_license("cust_compl", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if not db.scalars(select(License).where(License.jti == jti)).first():
            db.add(
                License(
                    jti=jti,
                    customer_email="x@x.com",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now,
                    expires_at=now + timedelta(days=30),
                    scheduled_delete_at=now + timedelta(days=30),
                )
            )
            db.commit()

    out = json.loads(asyncio.run(compliance_status()))
    assert out["deletions"]["pending"] >= 1


def test_compliance_status_registered_in_tool_count():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "compliance_status" in names
