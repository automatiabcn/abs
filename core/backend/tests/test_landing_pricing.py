"""Landing pricing data + checkout link tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.billing_v10.checkout_link import build_checkout_link

PRICING_PATH = (
    Path(__file__).resolve().parent.parent.parent / "landing/v10/pricing_data.json"
)


def test_pricing_data_loads() -> None:
    data = json.loads(PRICING_PATH.read_text("utf-8"))
    assert data["schema_version"] == 1
    assert data["currency"] == "USD"
    tier_ids = {t["id"] for t in data["tiers"]}
    assert {"solo", "team"} == tier_ids
    assert data["trial_days"] == 7


def test_pricing_data_has_three_locales() -> None:
    data = json.loads(PRICING_PATH.read_text("utf-8"))
    assert {"en", "tr", "es"} <= set(data["i18n"].keys())
    for locale in ("en", "tr", "es"):
        assert "pricing.cta.checkout" in data["i18n"][locale]


def test_build_checkout_link_uses_tenant_and_tier() -> None:
    url = build_checkout_link(
        base_url="https://abs.local/api",
        tier_id="team",
        tenant_id="t1",
        locale="tr",
    )
    assert url.startswith("https://abs.local/api/billing/checkout?")
    assert "tier=team" in url
    assert "tenant_id=t1" in url
    assert "locale=tr" in url
    # The smallest team we sell — not the cap. The default used to be the tier's
    # seat cap, which on a per-seat plan would open a checkout for 500 people.
    assert "seats=3" in url


def test_build_checkout_link_overrides_seat_count() -> None:
    url = build_checkout_link(
        base_url="https://abs.local/api",
        tier_id="team",
        tenant_id="t1",
        seat_count=7,
    )
    assert "seats=7" in url


def test_build_checkout_link_rejects_unknown_tier() -> None:
    with pytest.raises(ValueError):
        build_checkout_link(
            base_url="https://abs.local/api",
            tier_id="enterprise",
            tenant_id="t1",
        )


def test_build_checkout_link_requires_tenant() -> None:
    with pytest.raises(ValueError):
        build_checkout_link(
            base_url="https://abs.local/api",
            tier_id="team",
            tenant_id="",
        )
