"""Panel SSE _build_budget real today_usd + learnings_count tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def test_build_budget_uses_real_cost(monkeypatch, isolated_data_dir):
    """estimate_daily_cost mock → _build_budget should use these values."""
    from app.api import stream as stream_mod
    import app.billing.cost_estimator as cost_mod

    fake_cost = {
        "today_usd": 1.23,
        "projected_monthly_usd": 36.90,
        "by_provider": {"groq": 1.23},
        "breakdown": [],
        "estimated_at": 0.0,
        "note": "test",
    }
    monkeypatch.setattr(cost_mod, "estimate_daily_cost", lambda: fake_cost)
    # let's patch the billing/__init__ re-export so that app.api.stream imports correctly
    import app.billing as billing_pkg

    monkeypatch.setattr(
        billing_pkg, "estimate_daily_cost", lambda: fake_cost, raising=False
    )

    payload = stream_mod._build_budget()
    assert payload["today_usd"] == 1.23
    assert payload["projected_monthly_usd"] == 36.90


def test_build_budget_uses_real_learnings(monkeypatch, isolated_data_dir):
    """recent_count mock → learnings_count that value."""
    from app.api import stream as stream_mod
    import app.learnings.store as learnings_mod

    monkeypatch.setattr(learnings_mod, "recent_count", lambda window_days=30: 7)
    payload = stream_mod._build_budget()
    assert payload["learnings_count"] == 7


def test_cache_stats_returns_real_counter(monkeypatch):
    """default_cache hit/miss counter returns real values to MCP cache_stats."""
    from app.cascade import cache as cache_mod
    from app.cascade.cache import SemanticCache, prompt_hash
    from app.providers.schemas import ProviderResponse

    fresh = SemanticCache()
    monkeypatch.setattr(cache_mod, "default_cache", fresh)

    import asyncio

    async def _exercise():
        key = prompt_hash("foo", "m1")
        await fresh.get(key)  # miss
        await fresh.set(
            key, ProviderResponse(text="x", model="m1", provider="p", elapsed_ms=1)
        )
        await fresh.get(key)  # hit
        await fresh.get(prompt_hash("bar", "m1"))  # miss

    asyncio.run(_exercise())
    s = fresh.stats()
    assert s["hits"] == 1
    assert s["misses"] == 2
    assert s["entries"] == 1
    assert 0 < s["hit_rate_pct"] < 100
