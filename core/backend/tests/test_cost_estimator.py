"""Daily cost estimator testleri (tracker × provider_configs)."""

from __future__ import annotations


def _fake_snapshot(payload: dict) -> dict:
    """tracker.snapshot() format: {tool: {count_total, count_24h, last_called_at}}."""
    return {
        name: {"count_total": v, "count_24h": v, "last_called_at": 0.0}
        for name, v in payload.items()
    }


def test_estimate_returns_zero_when_no_usage(monkeypatch):
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(tracker, "snapshot", lambda: {})
    out = cost_estimator.estimate_daily_cost()
    assert out["today_usd"] == 0.0
    assert out["projected_monthly_usd"] == 0.0
    assert out["breakdown"] == []


def test_estimate_with_one_tool_call(monkeypatch):
    """Anthropic claude-haiku 100 call → today_usd > 0, breakdown[0].tool == ask_claude-haiku."""
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    # claude-haiku alias exists → ask_claude-haiku tool name
    monkeypatch.setattr(
        tracker, "snapshot", lambda: _fake_snapshot({"ask_claude-haiku": 100})
    )
    out = cost_estimator.estimate_daily_cost()
    assert out["today_usd"] > 0
    assert "anthropic" in out["by_provider"]
    assert len(out["breakdown"]) >= 1
    top = out["breakdown"][0]
    assert top["tool"] == "ask_claude-haiku"
    assert top["provider"] == "anthropic"
    assert top["calls_24h"] == 100


def test_unknown_tool_skipped(monkeypatch):
    """provider_configs'ta olmayan tool 0 USD getirir."""
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(
        tracker, "snapshot", lambda: _fake_snapshot({"ask_foobar_unknown": 5000})
    )
    out = cost_estimator.estimate_daily_cost()
    assert out["today_usd"] == 0.0
    assert out["breakdown"] == []


def test_breakdown_sorted_by_cost(monkeypatch):
    """2 tool: claude-opus expensive (15.0/75.0), gemini-flash-lite cheap (0.0375/0.15)."""
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(
        tracker,
        "snapshot",
        lambda: _fake_snapshot({"ask_claude-opus": 50, "ask_gemini-flash-lite": 50}),
    )
    out = cost_estimator.estimate_daily_cost()
    assert len(out["breakdown"]) >= 2
    # claude-opus is more expensive → first priority
    assert out["breakdown"][0]["tool"] == "ask_claude-opus"
    assert out["breakdown"][0]["estimated_usd"] > out["breakdown"][1]["estimated_usd"]


def test_estimate_includes_note_about_token_estimation(monkeypatch):
    from app.billing import cost_estimator
    from app.mcp.tracking import tracker

    monkeypatch.setattr(tracker, "snapshot", lambda: {})
    out = cost_estimator.estimate_daily_cost()
    assert "note" in out
    assert "1500" in out["note"]
