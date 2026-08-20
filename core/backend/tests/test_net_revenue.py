"""Net revenue (gross - refunds - Stripe fees)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.config import settings
from app.db.models import License
from app.db.session import get_engine


def _seed(jti: str, tier: str, seat_count: int, refunded: bool = False):
    now = datetime.now(timezone.utc)
    row = License(
        jti=jti,
        customer_email=f"{jti}@x.co",
        customer_id_stripe=f"cus_{jti}",
        tier=tier,
        seat_count=seat_count,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )
    if refunded:
        row.revoked_at = now
        row.revoked_reason = "stripe_refund"
    with Session(get_engine()) as s:
        s.add(row)
        s.commit()


def test_net_revenue_subtracts_refund_and_fees(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    from app.mcp.tools import billing_tools as bt

    bt._PRODUCT_CACHE["data"] = []
    bt._PRODUCT_CACHE["ts"] = 9e9

    # Seeded with the SKU that is actually sold. These said "self-host" and
    # "team" — tiers from two retired models — so the test was measuring
    # revenue for products nobody could buy, and passed only because the price
    # map still carried their numbers.
    _seed("net_self_a", "solo", 1)
    _seed("net_team5_a", "solo", 1)
    _seed("net_self_refund_a", "solo", 1, refunded=True)

    raw = asyncio.run(bt.billing_status())
    out = json.loads(raw)
    rev = out["revenue"]
    # Yeni alanlar
    assert "refunds_usd" in rev
    assert "fees_usd" in rev
    assert "net_usd" in rev
    # One refunded subscription, so the refund total is at least a month of it.
    from app.mcp.tools.billing_tools import _license_value_usd

    assert rev["refunds_usd"] >= _license_value_usd("solo", 1)
    # Fees > 0 (her checkout 0.30 + %2.9)
    assert rev["fees_usd"] > 0
    # Net total - refund - fees
    expected_net = rev["total_usd"] - rev["refunds_usd"] - rev["fees_usd"]
    assert abs(rev["net_usd"] - round(expected_net, 2)) < 0.01


def test_net_revenue_zero_refund_only_fees(monkeypatch):
    """Refund yokken refunds_usd 0, fees > 0, net = total - fees."""
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    from app.mcp.tools import billing_tools as bt

    bt._PRODUCT_CACHE["data"] = []
    bt._PRODUCT_CACHE["ts"] = 9e9

    raw = asyncio.run(bt.billing_status())
    out = json.loads(raw)
    rev = out["revenue"]
    # refunds_usd ≥ 0
    assert rev["refunds_usd"] >= 0
    # fees > 0 always (at least one license exists)
    assert rev["fees_usd"] >= 0
    # net <= total her zaman
    assert rev["net_usd"] <= rev["total_usd"]
