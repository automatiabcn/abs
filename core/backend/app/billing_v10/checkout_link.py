# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Checkout deep-link helper for the landing pricing page.

Builds a stable URL the frontend can hit to start the Stripe checkout for a
given tier + tenant. Does NOT call Stripe — the actual session creation lives
behind the existing `/v1/billing/checkout` API which the frontend hits via
fetch (T-058 wires the route).
"""

from __future__ import annotations

from urllib.parse import urlencode

from app.billing_v10.seats import TIERS

__all__ = ["build_checkout_link"]


def build_checkout_link(
    *,
    base_url: str,
    tier_id: str,
    tenant_id: str,
    locale: str = "en",
    seat_count: int | None = None,
) -> str:
    if tier_id not in TIERS:
        raise ValueError(f"unknown tier {tier_id!r}")
    if not tenant_id:
        raise ValueError("tenant_id required")
    seats = seat_count if seat_count is not None else TIERS[tier_id].seat_cap
    qs = urlencode(
        {
            "tier": tier_id,
            "tenant_id": tenant_id,
            "locale": locale,
            "seats": str(seats),
        }
    )
    return f"{base_url.rstrip('/')}/billing/checkout?{qs}"
