# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""015/017 — Billing + learnings MCP tool'lari.

015: daily_cost, learnings_recent, learnings_log
017: billing_status (Stripe + lisans + revenue + son 10 webhook event)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import List, Optional

# REGISTERED_TOOLS must be defined BEFORE importing app.mcp.server,
# because mcp_server import triggers register_all_tools() which inspects this.
REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


# 017 — billing_status helpers (lazy imports to avoid circular import at boot)
_PRODUCT_CACHE: dict = {"data": None, "ts": 0.0}
_PRODUCT_CACHE_TTL = 300  # 5 dk

# 011 SKU pricing — tier × seat_count → USD
_PRICE_MAP = {
    ("self-host", 1): 299,
    ("team", 5): 1196,
    ("team", 10): 2093,
}


def _get_products_cached() -> list[dict]:
    from app.config import settings

    now = time.time()
    if _PRODUCT_CACHE["data"] is not None and (now - _PRODUCT_CACHE["ts"] < _PRODUCT_CACHE_TTL):
        return _PRODUCT_CACHE["data"]
    if not settings.stripe_secret_key:
        return []
    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        products = stripe.Product.list(active=True, limit=10)
        out: list[dict] = []
        for p in products.data:
            meta = getattr(p, "metadata", None) or {}
            sku = meta.get("sku", "?")
            mode = meta.get("mode", "?")
            prices = stripe.Price.list(product=p.id, active=True, limit=1)
            amount = prices.data[0].unit_amount if prices.data else 0
            out.append(
                {
                    "sku": sku,
                    "name": getattr(p, "name", "?"),
                    "price_usd": amount / 100,
                    "mode": mode,
                }
            )
        _PRODUCT_CACHE["data"] = out
        _PRODUCT_CACHE["ts"] = now
        return out
    except Exception:
        return []


def _compute_revenue(db) -> dict:
    """Lisans kayitlarinin tier × seat fiyat toplamindan revenue.

    022 — Net revenue: gross - refunds - Stripe fees.
    Stripe fee modeli: %2.9 + $0.30 her başarılı checkout'ta (EU resident kart).
    """
    from sqlmodel import select

    from app.db.models import License

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    mtd_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    licenses = db.scalars(select(License)).all()
    today_usd = 0.0
    mtd_usd = 0.0
    total_usd = 0.0
    refunds_usd = 0.0
    fees_usd = 0.0
    for lic in licenses:
        amount = _PRICE_MAP.get((lic.tier, lic.seat_count), 0)
        total_usd += amount
        issued_at = lic.issued_at
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)
        if issued_at >= mtd_start:
            mtd_usd += amount
        if issued_at >= today_start:
            today_usd += amount
        # 022 — Stripe fee tahmini her başarılı checkout için
        fees_usd += amount * 0.029 + 0.30
        if lic.revoked_at is not None and lic.revoked_reason == "stripe_refund":
            refunds_usd += amount

    net_usd = total_usd - refunds_usd - fees_usd

    return {
        "today_usd": round(today_usd, 2),
        "mtd_usd": round(mtd_usd, 2),
        "total_usd": round(total_usd, 2),
        "refunds_usd": round(refunds_usd, 2),
        "fees_usd": round(fees_usd, 2),
        "net_usd": round(net_usd, 2),
    }


def _license_counts(db) -> dict:
    from sqlmodel import select

    from app.db.models import License

    now = datetime.now(timezone.utc)
    licenses = db.scalars(select(License)).all()
    active = 0
    revoked = 0
    expired = 0
    for lic in licenses:
        if lic.revoked_at is not None:
            revoked += 1
            continue
        expires_at = lic.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            expired += 1
        else:
            active += 1
    return {"active": active, "revoked": revoked, "expired": expired}


def _recent_events(db, limit: int = 10) -> list[dict]:
    from sqlmodel import select

    from app.db.models import WebhookEvent

    rows = db.scalars(
        select(WebhookEvent)
        .order_by(WebhookEvent.received_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    ).all()
    out: list[dict] = []
    for r in rows:
        received = r.received_at
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        out.append(
            {
                "event_id": r.event_id,
                "event_type": r.event_type,
                "received_at": received.isoformat(),
                "license_jti": r.license_jti,
            }
        )
    return out


@mcp_server.tool()
@with_hooks("daily_cost")
async def daily_cost() -> str:
    """tracker × provider_configs pricing → bugunku tahmini maliyet.

    Sprint 2N FAZ E (P1 #2M-014) — provider-free customer'da
    estimate_daily_cost veya tracker.snapshot içinde IndexError oluşursa
    stack trace MCP client'a sızıyordu. Empty fallback shape döndür.
    """
    await tracker.bump("daily_cost")
    from app.billing.cost_estimator import estimate_daily_cost

    try:
        payload = estimate_daily_cost()
    except (IndexError, KeyError) as exc:
        payload = {
            "today_usd": 0.0,
            "projected_monthly_usd": 0.0,
            "by_provider": {},
            "breakdown": [],
            "estimated_at": __import__("time").time(),
            "note": (
                "Maliyet verisi henüz yok — provider konfigürasyonu veya "
                "tracker geçmişi eksik."
            ),
            "_diagnostic": f"{type(exc).__name__}: {exc}",
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("learnings_recent")
async def learnings_recent(limit: int = 20) -> str:
    """Son N learning kaydi + kategorik istatistikler."""
    await tracker.bump("learnings_recent")
    from app.learnings.store import recent, stats

    return json.dumps(
        {"recent": recent(limit=limit), "stats": stats()},
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("learnings_log")
async def learnings_log(
    category: str, lesson: str, project: Optional[str] = None
) -> str:
    """Manuel learning ekle. category: bugfix|delegation|arch|security|perf|ux."""
    await tracker.bump("learnings_log")
    from app.learnings.store import log

    h = log(category, lesson, source="mcp_tool", project=project)
    return json.dumps({"ok": h is not None, "hash": h}, ensure_ascii=False)


@mcp_server.tool()
@with_hooks("billing_status")
async def billing_status() -> str:
    """017 — ABS billing dashboard: Stripe + DB lisans + son 10 webhook event."""
    await tracker.bump("billing_status")
    from app.config import settings
    from app.db.session import get_session_sync

    with get_session_sync() as db:
        out = {
            "stripe_configured": bool(settings.stripe_secret_key),
            "products": _get_products_cached(),
            "revenue": _compute_revenue(db),
            "licenses": _license_counts(db),
            "recent_events": _recent_events(db),
        }
    return json.dumps(out, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(
    ["daily_cost", "learnings_recent", "learnings_log", "billing_status"]
)
