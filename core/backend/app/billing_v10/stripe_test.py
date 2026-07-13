# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-042 — Stripe TEST-mode billing wrapper.

⚠ NEVER swap to live keys autonomously. The mode flip is a manual-approval
gate per the v10 worker brief. This module hard-asserts that the configured
key is a `sk_test_*` value when `enforce_test_mode=True` (default).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "BillingMisconfiguration",
    "CheckoutSession",
    "Subscription",
    "StripeBilling",
]


class BillingMisconfiguration(RuntimeError):
    """Raised on live-key usage without explicit override + on missing config."""


@dataclass(slots=True)
class CheckoutSession:
    session_id: str
    tenant_id: str
    price_id: str
    seat_count: int
    success_url: str
    cancel_url: str
    created_at: float


@dataclass(slots=True)
class Subscription:
    subscription_id: str
    tenant_id: str
    price_id: str
    seat_count: int
    status: str  # trialing | active | past_due | canceled
    metadata: dict[str, str] = field(default_factory=dict)


class StripeBilling:
    backend: str

    def __init__(
        self,
        *,
        backend: str = "test",
        enforce_test_mode: bool = True,
    ) -> None:
        self.backend = backend
        if backend not in {"test", "live"}:
            raise ValueError(f"unsupported stripe backend: {backend}")
        self._key = getattr(settings, "stripe_secret_key", "") or ""
        if backend == "test" and enforce_test_mode and self._key:
            if not self._key.startswith(("sk_test_", "rk_test_")):
                raise BillingMisconfiguration(
                    "stripe_secret_key must be sk_test_* in TEST mode"
                )
        if backend == "live" and not self._key.startswith(("sk_live_", "rk_live_")):
            raise BillingMisconfiguration("live mode requires sk_live_* key")

        self._sessions: dict[str, CheckoutSession] = {}
        self._subs: dict[str, Subscription] = {}

    def create_checkout(
        self,
        *,
        tenant_id: str,
        price_id: str,
        seat_count: int,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        if not tenant_id or not price_id:
            raise ValueError("tenant_id + price_id required")
        if seat_count <= 0:
            raise ValueError("seat_count must be positive")
        session = CheckoutSession(
            session_id=f"cs_test_{uuid.uuid4().hex[:24]}",
            tenant_id=tenant_id,
            price_id=price_id,
            seat_count=seat_count,
            success_url=success_url,
            cancel_url=cancel_url,
            created_at=time.time(),
        )
        self._sessions[session.session_id] = session
        logger.info(
            "stripe_checkout tenant=%s price=%s seats=%d",
            tenant_id,
            price_id,
            seat_count,
        )
        return session

    def confirm_checkout(self, session_id: str) -> Subscription:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"checkout session {session_id!r} not found")
        sub = Subscription(
            subscription_id=f"sub_test_{uuid.uuid4().hex[:24]}",
            tenant_id=session.tenant_id,
            price_id=session.price_id,
            seat_count=session.seat_count,
            status="active",
        )
        self._subs[sub.subscription_id] = sub
        return sub

    def status(self, subscription_id: str) -> Subscription:
        sub = self._subs.get(subscription_id)
        if sub is None:
            raise KeyError(f"subscription {subscription_id!r} not found")
        return sub

    def cancel(self, subscription_id: str) -> Subscription:
        sub = self.status(subscription_id)
        sub.status = "canceled"
        return sub
