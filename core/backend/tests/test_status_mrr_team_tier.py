# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Monthly revenue, from a monthly product.

The MRR estimate used to key its price table on exact (tier, seat_count) pairs —
("team", 5) and ("team", 10) — because the plans were fixed packs. A team of six
matched no key and contributed nothing at all. The plans are per seat now, so the
sum is a multiplication, and every team counts for what it actually pays.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.api.status_page import _mrr_estimate_usd
from app.config import settings
from app.db.models import License
from app.db.session import get_engine


def test_team_licence_counts_toward_mrr(client, monkeypatch):
    monkeypatch.setattr(settings, "abs_seat_price_team", 19.0)  # per seat, per month
    with Session(get_engine()) as db:
        db.add(
            License(
                jti="mrr-team-tier-1",
                tier="team",
                seat_count=5,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    # Five seats at $19. Before this, a team of any size the price table did not
    # name by hand contributed $0.
    assert _mrr_estimate_usd() >= 95


def test_a_team_of_six_is_not_worth_nothing(client, monkeypatch):
    """The size that fell between the packs, and silently earned us nothing."""
    monkeypatch.setattr(settings, "abs_seat_price_team", 19.0)
    with Session(get_engine()) as db:
        db.add(
            License(
                jti="mrr-team-of-six",
                tier="team",
                seat_count=6,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    assert _mrr_estimate_usd() >= 114  # 6 x 19
