"""T-043 — Tier + seat enforcement tests."""

from __future__ import annotations

import pytest

from app.billing_v10.seats import (
    SeatCounter,
    SeatLimitExceeded,
    TIERS,
    tier_for_seats,
)


def test_tier_for_seats_returns_smallest_fitting_tier() -> None:
    assert tier_for_seats(1).name == "self-host"
    assert tier_for_seats(3).name == "team-5"
    assert tier_for_seats(8).name == "team-10"


def test_tier_for_seats_rejects_zero_and_negative() -> None:
    with pytest.raises(ValueError):
        tier_for_seats(0)


def test_tier_for_seats_above_cap_raises() -> None:
    with pytest.raises(SeatLimitExceeded):
        tier_for_seats(50)


def test_seat_counter_lifecycle() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="team-5")
    assert sc.add(tenant_id="t1", n=3) == 3
    assert sc.usage("t1")["in_use"] == 3
    sc.remove(tenant_id="t1", n=1)
    assert sc.usage("t1")["in_use"] == 2


def test_seat_counter_blocks_over_cap() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="self-host")
    with pytest.raises(SeatLimitExceeded):
        sc.add(tenant_id="t1", n=2)


def test_initialise_rejects_initial_overflow() -> None:
    sc = SeatCounter()
    with pytest.raises(SeatLimitExceeded):
        sc.initialise(tenant_id="t1", tier="self-host", in_use=2)


def test_unknown_tier_raises() -> None:
    sc = SeatCounter()
    with pytest.raises(ValueError):
        sc.initialise(tenant_id="t1", tier="enterprise")


def test_upgrade_requires_known_tier_and_capacity() -> None:
    sc = SeatCounter()
    sc.initialise(tenant_id="t1", tier="team-5")
    sc.add(tenant_id="t1", n=4)
    with pytest.raises(SeatLimitExceeded):
        sc.upgrade(tenant_id="t1", new_tier="self-host")
    sc.upgrade(tenant_id="t1", new_tier="team-10")
    assert sc.usage("t1")["tier"] == "team-10"


def test_tiers_constant_includes_three_canonical_tiers() -> None:
    assert {"self-host", "team-5", "team-10"} <= set(TIERS.keys())


def test_unknown_tenant_raises_keyerror() -> None:
    sc = SeatCounter()
    with pytest.raises(KeyError):
        sc.add(tenant_id="ghost")
