# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A quota that has run out is not a missing key.

When a provider stops answering because its allowance is spent, the useful
sentence is **when it comes back** — not "buy another one". Daily allowances
reset at UTC midnight; a per-minute limit clears while you read the message; a
429 cooldown can say how long it has left. Telling somebody to spend money on a
limit that lifts tonight is wrong twice: it costs them, and it teaches them the
product does not understand its own state.

These tests pin the translation from the meter's machine codes into that
sentence, and they pin the one word that must never appear in it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.capabilities import minutes_to_utc_midnight, rest_reason

# 16:20 UTC — 7h40m before the daily counters roll over.
NOW = datetime(2026, 8, 2, 16, 20, tzinfo=timezone.utc)
TO_MIDNIGHT = minutes_to_utc_midnight(NOW)


@pytest.mark.parametrize(
    "code",
    ["rpd_exhausted_1000", "tpd_exhausted_50000", "neurons_exhausted_10000"],
)
def test_a_spent_daily_allowance_says_when_it_renews(code):
    msg = rest_reason(code, minutes_to_utc_midnight=TO_MIDNIGHT)
    assert "renews at midnight UTC" in msg
    assert "7 hours 40 minutes" in msg, msg
    # The whole point: this is not a purchase decision.
    assert "buy" not in msg.lower()
    assert "key" not in msg.lower()


def test_a_per_minute_limit_says_it_clears_by_itself():
    msg = rest_reason("rpm_full_30", minutes_to_utc_midnight=TO_MIDNIGHT)
    assert "per-minute" in msg
    assert "clears" in msg
    assert "buy" not in msg.lower()


def test_a_cooldown_reports_the_time_it_has_left():
    assert "45 seconds" in rest_reason("cooldown_45s", minutes_to_utc_midnight=TO_MIDNIGHT)
    # Long cooldowns read better in minutes than in three-digit seconds.
    assert "10 minutes" in rest_reason("cooldown_600s", minutes_to_utc_midnight=TO_MIDNIGHT)
    # A cooldown with no number still says what is happening.
    assert "backing off" in rest_reason("cooldown_", minutes_to_utc_midnight=TO_MIDNIGHT)


def test_a_tripped_breaker_says_it_retries_itself():
    msg = rest_reason("breaker_open", minutes_to_utc_midnight=TO_MIDNIGHT)
    assert "retries by itself" in msg
    assert "buy" not in msg.lower()


def test_an_unknown_code_admits_it_rather_than_inventing_a_cause():
    msg = rest_reason("something_new_upstream", minutes_to_utc_midnight=TO_MIDNIGHT)
    assert msg == "cannot answer right now"
    assert "midnight" not in msg, "a guess about renewal is worse than no guess"


def test_the_countdown_is_measured_from_the_clock_not_assumed():
    # Just before midnight the wait is minutes, not "tomorrow".
    late = minutes_to_utc_midnight(datetime(2026, 8, 2, 23, 45, tzinfo=timezone.utc))
    assert late == 15
    assert "15 minutes" in rest_reason("rpd_exhausted_1", minutes_to_utc_midnight=late)
    # Exactly at midnight the counters have just rolled: a full day, not zero.
    assert minutes_to_utc_midnight(datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)) == 24 * 60


def test_singulars_read_like_english():
    assert "1 minute" in rest_reason(
        "rpd_exhausted_1", minutes_to_utc_midnight=1
    )
    assert "1 hour" in rest_reason("rpd_exhausted_1", minutes_to_utc_midnight=60)
    assert "1 hour 1 minute" in rest_reason("rpd_exhausted_1", minutes_to_utc_midnight=61)
