"""016 — Real token tracking + cost_estimator gerçek/fallback testleri."""

from __future__ import annotations

import pytest


def _fake_snap(payload: dict) -> dict:
    """tracker.snapshot() formatı."""
    out = {}
    for name, v in payload.items():
        if isinstance(v, int):
            out[name] = {
                "count_total": v,
                "count_24h": v,
                "last_called_at": 0.0,
                "tokens_in_24h": 0,
                "tokens_out_24h": 0,
            }
        else:
            out[name] = {
                "count_total": v.get("count_24h", 0),
                "count_24h": v.get("count_24h", 0),
                "last_called_at": 0.0,
                "tokens_in_24h": v.get("tokens_in_24h", 0),
                "tokens_out_24h": v.get("tokens_out_24h", 0),
            }
    return out


@pytest.mark.asyncio
async def test_tracker_bump_accepts_tokens():
    from app.mcp.tracking import UsageTracker

    t = UsageTracker()
    await t.bump("ask_test", tokens_in=100, tokens_out=200)
    snap = t.snapshot()
    assert snap["ask_test"]["count_24h"] == 1
    assert snap["ask_test"]["tokens_in_24h"] == 100
    assert snap["ask_test"]["tokens_out_24h"] == 200


@pytest.mark.asyncio
async def test_tracker_bump_accumulates():
    from app.mcp.tracking import UsageTracker

    t = UsageTracker()
    await t.bump("ask_test", tokens_in=100, tokens_out=200)
    await t.bump("ask_test", tokens_in=50, tokens_out=80)
    await t.bump("ask_test", tokens_in=10, tokens_out=20)
    snap = t.snapshot()
    assert snap["ask_test"]["count_24h"] == 3
    assert snap["ask_test"]["tokens_in_24h"] == 160
    assert snap["ask_test"]["tokens_out_24h"] == 300


@pytest.mark.asyncio
async def test_tracker_bump_backward_compat_no_tokens():
    """Eski signature `bump(name)` hala calismali (default 0)."""
    from app.mcp.tracking import UsageTracker

    t = UsageTracker()
    await t.bump("ask_legacy")
    snap = t.snapshot()
    assert snap["ask_legacy"]["count_24h"] == 1
    assert snap["ask_legacy"]["tokens_in_24h"] == 0
    assert snap["ask_legacy"]["tokens_out_24h"] == 0


def test_cost_estimator_uses_real_tokens_when_available(monkeypatch):
    """Gercek token sayilari varsa breakdown.exact=True, hesap dogru."""
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(
        tracker,
        "snapshot",
        lambda: _fake_snap(
            {
                "ask_claude-haiku": {
                    "count_24h": 10,
                    "tokens_in_24h": 5000,
                    "tokens_out_24h": 2000,
                }
            }
        ),
    )
    out = cost_estimator.estimate_daily_cost()
    assert out["today_usd"] > 0
    assert len(out["breakdown"]) == 1
    top = out["breakdown"][0]
    assert top["exact"] is True
    assert top["tokens_in"] == 5000
    assert top["tokens_out"] == 2000
    assert "Gercek token tracking aktif" in out["note"]


def test_cost_estimator_falls_back_to_avg(monkeypatch):
    """Token 0 + count_24h>0 → 1500 avg fallback."""
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(
        tracker,
        "snapshot",
        lambda: _fake_snap(
            {
                "ask_claude-haiku": {
                    "count_24h": 10,
                    "tokens_in_24h": 0,
                    "tokens_out_24h": 0,
                }
            }
        ),
    )
    out = cost_estimator.estimate_daily_cost()
    assert out["today_usd"] > 0
    top = out["breakdown"][0]
    assert top["exact"] is False
    # avg 1500/call * 10 calls * 0.3 = 4500 in, 10500 out
    assert top["tokens_in"] == 4500
    assert top["tokens_out"] == 10500


def test_step_meta_tokens_forwarded(monkeypatch):
    """timed_step ProviderResponse.tokens_in/out → step.meta'ya yazsın."""
    import asyncio

    from app.pipelines.execution import timed_step
    from app.providers.schemas import ProviderResponse

    async def _fake_call():
        return ProviderResponse(
            text="ok", model="m1", provider="p", elapsed_ms=10,
            tokens_in=42, tokens_out=88,
        )

    step, _ = asyncio.run(timed_step("test", _fake_call(), model_hint="m1"))
    assert step.meta.get("tokens_in") == 42
    assert step.meta.get("tokens_out") == 88
