# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""How many people this server is licensed for, and how many it has.

The pricing page sold "5 named operator seats" for $1,196. The licence key
carried a `seat_count`. And `seat_count` was read in exactly zero places: a
customer could buy the single-seat plan and add fifty people, and nothing
anywhere would notice. We were selling a limit that did not exist.

Now the plan is a monthly subscription — solo, or a team priced per seat — so the
number has to mean something. It means this:

    no licence (trial)  → one person. The trial is for evaluating the product,
                          and a person can evaluate it alone.
    a licence           → exactly the seats it was issued for.

Refusing the *next* invite is the only fair place to draw the line. Locking out
people who are already in — because a subscription lapsed, or someone downgraded
— would mean a customer's colleagues lose their accounts over a billing event,
and accounts are not the thing we are selling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# What an unlicensed server (a trial) is allowed. One person, the one evaluating.
TRIAL_SEATS = 1


@dataclass(frozen=True)
class Seats:
    licensed: int
    used: int

    @property
    def room(self) -> int:
        return max(0, self.licensed - self.used)

    @property
    def full(self) -> bool:
        return self.used >= self.licensed


def licensed_seats() -> int:
    """The seat count on the key, or the trial's single seat when there is none."""
    token = (settings.license_key or "").strip()
    if not token:
        return TRIAL_SEATS
    try:
        from app.licensing import verify_license

        payload = verify_license(token)
        count = int(payload.get("seat_count") or 0)
        return count if count >= 1 else TRIAL_SEATS
    except Exception as exc:  # noqa: BLE001 — an unreadable key is not a bigger licence
        logger.warning("seat_count_unreadable err=%s", exc)
        return TRIAL_SEATS


def used_seats(tenant_id: str) -> int:
    """People who hold, or have been offered, a place on this server.

    A pending invite counts. It is a seat that has been given away — the person it
    was sent to can walk in with it — and a limit that only counts the people who
    have already accepted is a limit an admin can walk straight through by sending
    ten invitations at once.
    """
    from sqlmodel import Session, select

    from app.db.models import TenantInvite, User
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        # `User.tenant_slug`, not `tenant_id` — the invite table calls the same
        # thing by the other name, and counting the wrong column would have
        # returned zero people forever and enforced nothing.
        users = len(
            list(
                db.exec(
                    select(User).where(
                        User.tenant_slug == tenant_id,
                        User.status != "revoked",
                    )
                )
            )
        )
        pending = len(
            list(
                db.exec(
                    select(TenantInvite).where(
                        TenantInvite.tenant_id == tenant_id,
                        TenantInvite.status == "pending",
                    )
                )
            )
        )
    return users + pending


def status(tenant_id: str) -> Seats:
    return Seats(licensed=licensed_seats(), used=used_seats(tenant_id))


def refusal(seats: Seats) -> Optional[str]:
    """What to tell an admin who has just run out of seats. None when they have not.

    It says the number they have, the number they are using, and the one thing they
    can do about it — because "seat_limit_reached" tells a person nothing they did
    not already suspect.
    """
    if not seats.full:
        return None
    if seats.licensed <= TRIAL_SEATS and not (settings.license_key or "").strip():
        return (
            "The trial covers one person. To add your colleagues, subscribe to a "
            "team plan in the panel under Settings → Licence — seats are monthly, "
            "and you can change the number any time."
        )
    return (
        f"This subscription covers {seats.licensed} "
        f"{'seat' if seats.licensed == 1 else 'seats'}, and all of them are taken "
        f"({seats.used} in use, counting invitations that have not been accepted "
        "yet). Add seats under Settings → Licence, or remove someone first."
    )
