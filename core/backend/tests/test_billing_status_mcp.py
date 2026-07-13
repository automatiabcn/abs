"""017 — billing_status MCP tool: Stripe + revenue + license + recent events."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.config import settings
from app.db.models import License, WebhookEvent
from app.db.session import get_engine


def test_billing_status_no_stripe_returns_empty_products(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    # Cache'i temizle ki onceki testten gelmesin
    from app.mcp.tools import billing_tools as bt

    bt._PRODUCT_CACHE["data"] = None
    bt._PRODUCT_CACHE["ts"] = 0.0

    raw = asyncio.run(bt.billing_status())
    out = json.loads(raw)
    assert out["stripe_configured"] is False
    assert out["products"] == []
    assert "revenue" in out
    assert "licenses" in out
    assert "recent_events" in out


def test_billing_status_revenue_aggregation(monkeypatch):
    """3 lisans (self-host + team-5 + team-10) → total_usd = 299 + 1196 + 2093."""
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    from app.mcp.tools import billing_tools as bt

    bt._PRODUCT_CACHE["data"] = []
    bt._PRODUCT_CACHE["ts"] = time.time()

    now = datetime.now(timezone.utc)
    seeds = [
        License(
            jti="jti_rev_self",
            customer_email="r1@x.co",
            customer_id_stripe="cus_r1",
            tier="self-host",
            seat_count=1,
            issued_at=now,
            expires_at=now + timedelta(days=365),
        ),
        License(
            jti="jti_rev_team5",
            customer_email="r2@x.co",
            customer_id_stripe="cus_r2",
            tier="team",
            seat_count=5,
            issued_at=now,
            expires_at=now + timedelta(days=365),
        ),
        License(
            jti="jti_rev_team10",
            customer_email="r3@x.co",
            customer_id_stripe="cus_r3",
            tier="team",
            seat_count=10,
            issued_at=now,
            expires_at=now + timedelta(days=365),
        ),
    ]
    with Session(get_engine()) as s:
        for r in seeds:
            s.add(r)
        s.commit()

    raw = asyncio.run(bt.billing_status())
    out = json.loads(raw)
    rev = out["revenue"]
    # Bu testte seeded 3 lisans + onceki testlerden de bazilari olabilir, ama
    # 299+1196+2093 = 3588 minimum
    assert rev["total_usd"] >= 3588
    assert rev["mtd_usd"] >= 3588
    assert rev["today_usd"] >= 3588
    # Lisans counts
    assert out["licenses"]["active"] >= 3


def test_billing_status_recent_events_ordered_desc(monkeypatch):
    """WebhookEvent insert order: son 10 newest-first döner."""
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    from app.mcp.tools import billing_tools as bt

    bt._PRODUCT_CACHE["data"] = []
    bt._PRODUCT_CACHE["ts"] = time.time()

    base = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        for i in range(3):
            s.add(
                WebhookEvent(
                    event_id=f"evt_order_{i}",
                    event_type="checkout.session.completed",
                    received_at=base + timedelta(seconds=i),
                )
            )
        s.commit()

    raw = asyncio.run(bt.billing_status())
    out = json.loads(raw)
    ev_ids = [e["event_id"] for e in out["recent_events"]]
    # En yeni eklenen (evt_order_2) listenin basinda olmali
    idx = {
        eid: ev_ids.index(eid)
        for eid in ("evt_order_0", "evt_order_1", "evt_order_2")
        if eid in ev_ids
    }
    assert idx["evt_order_2"] < idx["evt_order_1"] < idx["evt_order_0"]
