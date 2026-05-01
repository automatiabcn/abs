"""T-022 — LangFuse custom price tier tests."""

from __future__ import annotations

from app.observability.cost_table import (
    PRICING,
    PriceEntry,
    estimate_cost_usd,
    lookup,
    register,
)


def test_pricing_includes_groq_anthropic_self_host() -> None:
    keys = set(PRICING.keys())
    assert "groq:openai/gpt-oss-120b" in keys
    assert "anthropic:claude-opus-4" in keys
    assert "selfhost:bge-m3" in keys


def test_lookup_returns_entry_for_known_pair() -> None:
    e = lookup("anthropic", "claude-opus-4")
    assert e is not None
    assert e.input_per_million_usd == 15.0
    assert e.output_per_million_usd == 75.0


def test_lookup_returns_none_for_unknown() -> None:
    assert lookup("openai", "gpt-99-turbo") is None


def test_estimate_cost_usd_for_opus_call() -> None:
    cost = estimate_cost_usd(
        provider="anthropic",
        model="claude-opus-4",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    assert abs(cost - (15.0 + 75.0 * 0.5)) < 1e-6


def test_estimate_cost_returns_zero_for_unknown_pair() -> None:
    assert (
        estimate_cost_usd(
            provider="unknown",
            model="nope",
            input_tokens=1000,
            output_tokens=1000,
        )
        == 0.0
    )


def test_register_adds_entry() -> None:
    register(
        PriceEntry(
            provider="custom",
            model="test-model",
            input_per_million_usd=1.0,
            output_per_million_usd=2.0,
        )
    )
    e = lookup("custom", "test-model")
    assert e is not None
    assert e.input_per_million_usd == 1.0


def test_self_host_bge_costs_close_to_zero() -> None:
    cost = estimate_cost_usd(
        provider="selfhost",
        model="bge-m3",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert cost < 0.05
