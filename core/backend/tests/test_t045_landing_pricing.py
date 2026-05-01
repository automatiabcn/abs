"""T-045 — Landing pricing data + checkout link tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.billing_v10.checkout_link import build_checkout_link

PRICING_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "landing/v10/pricing_data.json"
)


def test_pricing_data_loads() -> None:
    data = json.loads(PRICING_PATH.read_text("utf-8"))
    assert data["schema_version"] == 1
    assert data["currency"] == "USD"
    tier_ids = {t["id"] for t in data["tiers"]}
    assert {"self-host", "team-5", "team-10"} == tier_ids


def test_pricing_data_has_three_locales() -> None:
    data = json.loads(PRICING_PATH.read_text("utf-8"))
    assert {"en", "tr", "es"} <= set(data["i18n"].keys())
    for locale in ("en", "tr", "es"):
        assert "pricing.cta.checkout" in data["i18n"][locale]


def test_build_checkout_link_uses_tenant_and_tier() -> None:
    url = build_checkout_link(
        base_url="https://abs.local/api",
        tier_id="team-5",
        tenant_id="t1",
        locale="tr",
    )
    assert url.startswith("https://abs.local/api/billing/checkout?")
    assert "tier=team-5" in url
    assert "tenant_id=t1" in url
    assert "locale=tr" in url
    assert "seats=5" in url


def test_build_checkout_link_overrides_seat_count() -> None:
    url = build_checkout_link(
        base_url="https://abs.local/api",
        tier_id="team-10",
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
            tier_id="team-5",
            tenant_id="",
        )
