"""beta_metrics MCP tool."""

from __future__ import annotations

import asyncio
import json

from sqlmodel import Session, select

from app.db.models import BetaRequest
from app.db.session import get_engine


def _wipe_beta_rows() -> None:
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            db.delete(r)
        db.commit()


def test_beta_metrics_response_shape():
    from app.mcp.tools.beta_tools import beta_metrics

    out = json.loads(asyncio.run(beta_metrics()))
    for key in (
        "pending",
        "approved",
        "rejected",
        "signups_24h",
        "signups_7d",
        "approved_to_paid",
        "approved_total",
        "conversion_rate",
    ):
        assert key in out, f"missing key: {key}"


def test_beta_metrics_reflects_pending_signups(client, monkeypatch):
    from app.config import settings
    from app.mcp.tools.beta_tools import beta_metrics

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    client.post("/v1/beta/request", json={"email": "m1@x.com", "lang": "en"})
    client.post("/v1/beta/request", json={"email": "m2@x.com", "lang": "tr"})

    out = json.loads(asyncio.run(beta_metrics()))
    assert out["pending"] >= 2
    assert out["signups_24h"] >= 2


def test_beta_metrics_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "beta_metrics" in names
