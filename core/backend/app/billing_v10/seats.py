"""T-043 — Pricing tier + seat enforcement (Self-host / Team-5 / Team-10).

Q12-R84: list-prices are read from settings (env). Defaults are 0.0; operators
MUST configure their own. Tier IDs are SKU keys, not prices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "SeatLimitExceeded",
    "Tier",
    "TIERS",
    "SeatCounter",
    "tier_for_seats",
]


class SeatLimitExceeded(RuntimeError):
    """Raised on seat add beyond tier cap."""


@dataclass(frozen=True, slots=True)
class Tier:
    name: str
    seat_cap: int
    monthly_price_usd: float
    stripe_price_setting: str  # name in Settings: e.g. "abs_price_self_host"


TIERS: dict[str, Tier] = {
    "self-host": Tier(
        name="self-host",
        seat_cap=1,
        monthly_price_usd=settings.abs_seat_price_self_host,
        stripe_price_setting="abs_price_self_host",
    ),
    "team-5": Tier(
        name="team-5",
        seat_cap=5,
        monthly_price_usd=settings.abs_seat_price_team_5,
        stripe_price_setting="abs_price_team_5",
    ),
    "team-10": Tier(
        name="team-10",
        seat_cap=10,
        monthly_price_usd=settings.abs_seat_price_team_10,
        stripe_price_setting="abs_price_team_10",
    ),
}


def tier_for_seats(seat_count: int) -> Tier:
    if seat_count <= 0:
        raise ValueError("seat_count must be positive")
    if seat_count <= 1:
        return TIERS["self-host"]
    if seat_count <= 5:
        return TIERS["team-5"]
    if seat_count <= 10:
        return TIERS["team-10"]
    raise SeatLimitExceeded(
        f"{seat_count} seats exceeds the highest published tier (10)"
    )


class SeatCounter:
    """Tenant-scoped seat ledger; production wraps the Stripe subscription
    quantity field but the same surface keeps tests offline."""

    def __init__(self) -> None:
        self._seats: dict[str, dict[str, int]] = {}  # tenant -> {tier, in_use}

    def initialise(self, *, tenant_id: str, tier: str, in_use: int = 0) -> None:
        if tier not in TIERS:
            raise ValueError(f"unknown tier {tier!r}")
        cap = TIERS[tier].seat_cap
        if in_use > cap:
            raise SeatLimitExceeded(
                f"{in_use} seats > tier {tier} cap {cap}"
            )
        self._seats[tenant_id] = {"tier": tier, "in_use": in_use}

    def add(self, *, tenant_id: str, n: int = 1) -> int:
        if tenant_id not in self._seats:
            raise KeyError(f"tenant {tenant_id!r} not initialised")
        record = self._seats[tenant_id]
        cap = TIERS[record["tier"]].seat_cap
        if record["in_use"] + n > cap:
            raise SeatLimitExceeded(
                f"adding {n} would exceed tier {record['tier']} cap {cap}"
            )
        record["in_use"] += n
        return record["in_use"]

    def remove(self, *, tenant_id: str, n: int = 1) -> int:
        record = self._seats.get(tenant_id)
        if record is None:
            raise KeyError(f"tenant {tenant_id!r} not initialised")
        record["in_use"] = max(0, record["in_use"] - n)
        return record["in_use"]

    def upgrade(self, *, tenant_id: str, new_tier: str) -> None:
        record = self._seats.get(tenant_id)
        if record is None:
            raise KeyError(f"tenant {tenant_id!r} not initialised")
        if new_tier not in TIERS:
            raise ValueError(f"unknown tier {new_tier!r}")
        cap = TIERS[new_tier].seat_cap
        if record["in_use"] > cap:
            raise SeatLimitExceeded(
                f"in-use {record['in_use']} > new tier cap {cap}"
            )
        record["tier"] = new_tier
        logger.info("seat_upgrade tenant=%s tier=%s", tenant_id, new_tier)

    def usage(self, tenant_id: str) -> dict[str, int | str]:
        record = self._seats.get(tenant_id)
        if record is None:
            raise KeyError(f"tenant {tenant_id!r} not initialised")
        return {**record, "cap": TIERS[record["tier"]].seat_cap}
