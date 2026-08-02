# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The ceiling the product promises, and the two ways a ceiling fails quietly.

The pivot document names opaque cost as the wound this product is built
against, and answers it with: your own key, a visible rate, **a hard cap**, a
cost you can see first.
Audited 2026-08-02 — the cap did not exist. Requests and tokens were counted;
money was not, and nothing stopped it.

A cap fails quietly in two ways, and both are tested here rather than assumed:

* it blocks free calls, so people turn it off and it protects nothing;
* it trusts a price it does not have, so an unpriced paid model spends without
  ever touching the counter. `estimate_cost_usd` returns 0.0 for a model it
  cannot find — which is exactly the shape of that hole.
"""

from __future__ import annotations

import pytest

from app.cascade import spend
from app.observability.cost_table import PriceEntry, register


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    spend.reset("t")
    # A known, easy-to-reason-about price: $1 per million in, $2 per million out.
    register(
        PriceEntry(
            provider="testcorp",
            model="big",
            input_per_million_usd=1.0,
            output_per_million_usd=2.0,
        )
    )
    yield
    spend.reset("t")


def _cap(monkeypatch, value: float) -> None:
    monkeypatch.setattr(spend, "cap_usd", lambda: value)


def test_no_ceiling_means_no_ceiling(monkeypatch):
    # Off is a deliberate choice, and while it is off nothing is refused.
    _cap(monkeypatch, 0)
    blocked, why = spend.would_exceed(provider="testcorp", model="big", tenant_id="t")
    assert blocked is False
    assert why == ""


def test_a_free_call_is_never_refused(monkeypatch):
    # ABS routes to free tiers first. Refusing a call that cannot spend
    # anything would be theatre, and people would switch the cap off.
    _cap(monkeypatch, 0.01)
    blocked, _ = spend.would_exceed(
        provider="groq", model="whatever", tenant_id="t", free=True
    )
    assert blocked is False


def test_spending_accumulates_and_the_ceiling_holds(monkeypatch):
    _cap(monkeypatch, 0.01)
    # 1M in + 1M out at the registered rate = $3.00, comfortably past a 1¢ cap.
    spend.record(
        provider="testcorp", model="big",
        input_tokens=1_000_000, output_tokens=1_000_000, tenant_id="t",
    )
    assert spend.spent_today("t") == pytest.approx(3.0)
    blocked, why = spend.would_exceed(provider="testcorp", model="big", tenant_id="t")
    assert blocked is True
    assert "$0.01 ceiling" in why
    assert "3.0000 used" in why


def test_a_refusal_says_when_it_lifts(monkeypatch):
    # "You are out" teaches nothing; "you are out until midnight" is the same
    # sentence a spent quota gets, and for the same reason.
    _cap(monkeypatch, 0.0001)
    _, why = spend.would_exceed(provider="testcorp", model="big", tenant_id="t")
    assert "resets at midnight UTC" in why
    assert "in " in why


def test_a_paid_model_with_no_price_is_refused_not_assumed_free(monkeypatch):
    # estimate_cost_usd returns 0.0 for a model it cannot find. Trusting that
    # is how an unpriced paid model spends forever without moving the counter.
    _cap(monkeypatch, 100.0)
    blocked, why = spend.would_exceed(
        provider="anthropic", model="some-unreleased-model", tenant_id="t"
    )
    assert blocked is True
    assert "no price" in why
    assert "ceiling" in why


def test_an_unpriced_call_makes_the_total_admit_it_is_a_floor(monkeypatch):
    _cap(monkeypatch, 100.0)
    spend.record(
        provider="anthropic", model="unknown-one",
        input_tokens=1000, output_tokens=1000, tenant_id="t",
    )
    s = spend.status("t")
    assert s["exact"] is False, "a total built from unpriced calls is a floor"
    assert s["unpriced_calls"] == 1
    # And a fully priced day says so.
    spend.reset("t")
    spend.record(
        provider="testcorp", model="big",
        input_tokens=1000, output_tokens=1000, tenant_id="t",
    )
    assert spend.status("t")["exact"] is True


def test_free_calls_never_touch_the_ledger(monkeypatch):
    _cap(monkeypatch, 100.0)
    added = spend.record(
        provider="groq", model="anything", input_tokens=999_999, output_tokens=999_999,
        tenant_id="t", free=True,
    )
    assert added == 0.0
    assert spend.spent_today("t") == 0.0


def test_the_day_rolls_over_at_utc_midnight(monkeypatch):
    _cap(monkeypatch, 100.0)
    spend.record(
        provider="testcorp", model="big",
        input_tokens=1_000_000, output_tokens=0, tenant_id="t",
    )
    assert spend.spent_today("t") == pytest.approx(1.0)
    # A new UTC day is a new ledger — the ceiling is daily, not lifetime.
    monkeypatch.setattr(spend, "_utc_today", lambda: "2999-01-01")
    assert spend.spent_today("t") == 0.0


def test_tenants_do_not_spend_each_others_budget(monkeypatch):
    _cap(monkeypatch, 100.0)
    spend.record(
        provider="testcorp", model="big",
        input_tokens=1_000_000, output_tokens=0, tenant_id="t",
    )
    assert spend.spent_today("t") == pytest.approx(1.0)
    assert spend.spent_today("someone-else") == 0.0
    spend.reset("someone-else")


def test_a_broken_price_lookup_does_not_break_the_call(monkeypatch):
    # A ledger that throws would take a working request down with it. The
    # number is worth less than the call.
    _cap(monkeypatch, 100.0)

    def _boom(**_kwargs):
        raise RuntimeError("pricing table unavailable")

    monkeypatch.setattr(spend, "estimate_cost_usd", _boom)
    assert spend.record(provider="testcorp", model="big", tenant_id="t") == 0.0
