"""Tier + seat enforcement tests."""

from __future__ import annotations

import pytest

from app.billing_v10.seats import (
    SeatCounter,
    SeatLimitExceeded,
    TIERS,
    tier_for_seats,
)


def test_tier_for_seats_returns_smallest_fitting_tier() -> None:
    assert tier_for_seats(1).name == "solo"
    assert tier_for_seats(3).name == "team"
    # A team of six could not be sold at all while the plans were 5- and 10-seat
    # packs. Per-seat pricing has nothing to fall between.
    assert tier_for_seats(6).name == "team"
    assert tier_for_seats(87).name == "team"


def test_tier_for_seats_rejects_zero_and_negative() -> None:
    with pytest.raises(ValueError):
        tier_for_seats(0)


def test_tier_for_seats_above_cap_raises() -> None:
    with pytest.raises(SeatLimitExceeded):
        tier_for_seats(5000)


def test_seat_counter_lifecycle() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="team")
    assert sc.add(tenant_id="t1", n=3) == 3
    assert sc.usage("t1")["in_use"] == 3
    sc.remove(tenant_id="t1", n=1)
    assert sc.usage("t1")["in_use"] == 2


def test_seat_counter_blocks_over_cap() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="solo")
    with pytest.raises(SeatLimitExceeded):
        sc.add(tenant_id="t1", n=2)


def test_initialise_rejects_initial_overflow() -> None:
    sc = SeatCounter()
    with pytest.raises(SeatLimitExceeded):
        sc.initialise(tenant_id="t1", tier="solo", in_use=2)


def test_unknown_tier_raises() -> None:
    sc = SeatCounter()
    with pytest.raises(ValueError):
        sc.initialise(tenant_id="t1", tier="enterprise")


def test_upgrade_requires_known_tier_and_capacity() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="team")
    sc.add(tenant_id="t1", n=4)
    with pytest.raises(SeatLimitExceeded):
        sc.upgrade(tenant_id="t1", new_tier="solo")
    sc.upgrade(tenant_id="t1", new_tier="team")
    assert sc.usage("t1")["tier"] == "team"


def test_tiers_constant_is_the_two_plans_on_sale() -> None:
    assert set(TIERS.keys()) == {"solo", "team"}


def test_unknown_tenant_raises_keyerror() -> None:
    sc = SeatCounter()
    with pytest.raises(KeyError):
        sc.add(tenant_id="ghost")
