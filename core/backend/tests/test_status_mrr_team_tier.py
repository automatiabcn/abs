# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (f) — 3rd-eye audit.

Regression: _mrr_estimate_usd keyed its price table by the strings "team-5" /
"team-10", but License.tier is "self-host" / "team" (seat_count distinguishes the
pack). So `r.tier in TIER_MONTHLY` was always False for team licences → every
team licence silently contributed $0 to the status-page MRR. Now keyed by
(tier, seat_count), matching billing_tools / status_tools.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.api.status_page import _mrr_estimate_usd
from app.config import settings
from app.db.models import License
from app.db.session import get_engine


def test_team_licence_counts_toward_mrr(client, monkeypatch):
    monkeypatch.setattr(settings, "abs_seat_price_team_5", 1200.0)  # → 100/mo
    with Session(get_engine()) as db:
        db.add(License(
            jti="mrr-team-tier-1", tier="team", seat_count=5,
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
        ))
        db.commit()

    # 1200 / 12 = 100 monthly. Before the fix the team licence matched no key
    # and contributed $0.
    assert _mrr_estimate_usd() >= 100
