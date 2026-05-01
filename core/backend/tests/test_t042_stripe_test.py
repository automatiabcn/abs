"""T-042 — Stripe TEST mode tests."""

from __future__ import annotations

import pytest

from app.billing_v10.stripe_test import (
    BillingMisconfiguration,
    StripeBilling,
)
from app.config import settings


@pytest.fixture(autouse=True)
def _stripe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)


def test_create_checkout_returns_session() -> None:
    b = StripeBilling()
    s = b.create_checkout(
        tenant_id="t1",
        price_id="price_self",
        seat_count=1,
        success_url="https://abs/ok",
        cancel_url="https://abs/no",
    )
    assert s.session_id.startswith("cs_test_")
    assert s.tenant_id == "t1"
    assert s.seat_count == 1


def test_confirm_checkout_returns_active_subscription() -> None:
    b = StripeBilling()
    s = b.create_checkout(
        tenant_id="t1",
        price_id="price_self",
        seat_count=1,
        success_url="https://abs/ok",
        cancel_url="https://abs/no",
    )
    sub = b.confirm_checkout(s.session_id)
    assert sub.status == "active"
    assert sub.tenant_id == "t1"


def test_status_unknown_raises() -> None:
    with pytest.raises(KeyError):
        StripeBilling().status("nope")


def test_cancel_marks_canceled() -> None:
    b = StripeBilling()
    s = b.create_checkout(
        tenant_id="t1",
        price_id="price_self",
        seat_count=1,
        success_url="https://abs/ok",
        cancel_url="https://abs/no",
    )
    sub = b.confirm_checkout(s.session_id)
    cancelled = b.cancel(sub.subscription_id)
    assert cancelled.status == "canceled"


def test_create_checkout_validates_inputs() -> None:
    b = StripeBilling()
    with pytest.raises(ValueError):
        b.create_checkout(
            tenant_id="",
            price_id="x",
            seat_count=1,
            success_url="a",
            cancel_url="b",
        )
    with pytest.raises(ValueError):
        b.create_checkout(
            tenant_id="t1",
            price_id="x",
            seat_count=0,
            success_url="a",
            cancel_url="b",
        )


def test_test_mode_blocks_live_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "stripe_secret_key", "sk_live_DANGER", raising=False
    )
    with pytest.raises(BillingMisconfiguration):
        StripeBilling(backend="test")


def test_live_mode_requires_live_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "stripe_secret_key", "sk_test_dummy", raising=False
    )
    with pytest.raises(BillingMisconfiguration):
        StripeBilling(backend="live")


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        StripeBilling(backend="nope")
