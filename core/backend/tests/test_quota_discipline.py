"""T-F03 — Claude monthly quota discipline + opt-in gate."""

from __future__ import annotations

import pathlib

import pytest

from app.observability import quota_monitor as qm


@pytest.fixture
def ledger(tmp_path, monkeypatch) -> pathlib.Path:
    path = tmp_path / "claude.jsonl"
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_LEDGER", str(path))
    monkeypatch.setenv("ABS_CLAUDE_MONTHLY_TOKEN_LIMIT", "1000000")
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_WARN_PCT", "0.8")
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_BLOCK_PCT", "0.95")
    return path


def test_status_zero_when_no_ledger(ledger):
    s = qm.status(ledger=ledger)
    assert s.used_tokens == 0
    assert s.used_pct == 0.0
    assert s.over_warn is False
    assert s.over_block is False


def test_record_increments_used(ledger):
    qm.record(tokens_in=1_000, tokens_out=500, model="claude-haiku-4-5", ledger=ledger)
    s = qm.status(ledger=ledger)
    assert s.used_tokens == 1_500


def test_warn_threshold_at_80_percent(ledger):
    # 800K of a 1M limit → should trigger over_warn but not over_block
    qm.record(
        tokens_in=400_000, tokens_out=400_000, model="claude-opus-4-5", ledger=ledger
    )
    s = qm.status(ledger=ledger)
    assert s.over_warn is True
    assert s.over_block is False
    assert "Claude budget" in (s.banner() or "")


def test_block_threshold_at_95_percent(ledger):
    qm.record(
        tokens_in=950_000, tokens_out=10_000, model="claude-opus-4-5", ledger=ledger
    )
    s = qm.status(ledger=ledger)
    assert s.over_block is True
    banner = s.banner() or ""
    assert "blocked" in banner.lower()


def test_gate_raises_at_block_threshold(ledger):
    qm.record(tokens_in=940_000, tokens_out=0, model="claude-opus-4-5", ledger=ledger)
    # current=940K, requesting 20K → projected=960K → above 95% (950K)
    with pytest.raises(qm.QuotaExceeded):
        qm.gate(requested_tokens=20_000, ledger=ledger)


def test_gate_passes_below_block(ledger):
    qm.record(tokens_in=500_000, tokens_out=0, model="claude-opus-4-5", ledger=ledger)
    s = qm.gate(requested_tokens=10_000, ledger=ledger)
    assert isinstance(s, qm.QuotaStatus)
    assert s.used_tokens == 500_000


def test_simulated_1m_token_run_progresses_through_thresholds(ledger):
    """Simulate 1M tokens in 100 chunks; verify warn fires before block."""
    saw_warn = False
    saw_block = False
    for _ in range(100):
        qm.record(
            tokens_in=10_000, tokens_out=0, model="claude-opus-4-5", ledger=ledger
        )
        s = qm.status(ledger=ledger)
        if s.over_warn and not saw_warn:
            saw_warn = True
        if s.over_block:
            saw_block = True
            break
    assert saw_warn, "warn threshold (80%) never tripped before block"
    assert saw_block, "block threshold (95%) never tripped"


def test_anthropic_provider_opt_in_default_off(monkeypatch):
    """T-F03 — default config never reaches Anthropic."""
    from app.config import settings
    from app.providers.anthropic import AnthropicProvider
    from app.providers.schemas import ProviderError

    monkeypatch.setattr(settings, "anthropic_enabled", False, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "anything", raising=False)
    provider = AnthropicProvider()

    import asyncio

    async def _go():
        with pytest.raises(ProviderError, match="opt-in"):
            await provider.call("hello")

    asyncio.run(_go())


def test_quota_monitor_record_isolated_per_ledger(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    qm.record(tokens_in=100, tokens_out=0, model="claude", ledger=a)
    qm.record(tokens_in=200, tokens_out=0, model="claude", ledger=b)
    assert qm.status(ledger=a).used_tokens == 100
    assert qm.status(ledger=b).used_tokens == 200


def test_reset_for_tests(ledger):
    qm.record(tokens_in=5, tokens_out=5, model="c", ledger=ledger)
    qm.reset_for_tests(ledger=ledger)
    assert qm.status(ledger=ledger).used_tokens == 0


def test_banner_none_when_under_warn(ledger):
    qm.record(tokens_in=100, tokens_out=0, model="c", ledger=ledger)
    s = qm.status(ledger=ledger)
    assert s.banner() is None
