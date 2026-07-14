"""`claude_tokens_used_pct_month` LangFuse score is wired.

PROMISE.md:
  "LangFuse dashboard `claude_tokens_used_pct_month` time-series."

Pinned contract:
  - When LangFuse is enabled and the SDK ships a `.score()` method,
    `quota_monitor.record(...)` pushes one score per recorded usage row,
    naming the metric `claude_tokens_used_pct_month` with the current
    `used_pct` ratio as the value.
  - When LangFuse is disabled, `record(...)` still completes without
    raising and emits zero scores (observability must never block the
    gate path).
"""

from __future__ import annotations

import pytest

from app.observability import quota_monitor


class _FakeLangfuse:
    def __init__(self) -> None:
        self.scores: list[dict] = []

    def score(self, **kwargs):
        self.scores.append(kwargs)


@pytest.fixture
def _ledger(tmp_path, monkeypatch):
    path = tmp_path / "claude_tokens.jsonl"
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_LEDGER", str(path))
    monkeypatch.setattr(quota_monitor, "_ledger_path", lambda: path)
    monkeypatch.setenv("ABS_CLAUDE_MONTHLY_TOKEN_LIMIT", "1000")
    return path


def test_promise_v5_score_pushed_when_langfuse_enabled(monkeypatch, _ledger):
    """Enabled LangFuse + working client → exactly one score per record()."""
    fake = _FakeLangfuse()
    from app.observability import langfuse_client as lf

    monkeypatch.setattr(lf, "is_enabled", lambda: True)
    monkeypatch.setattr(lf, "get_langfuse", lambda: fake)
    quota_monitor.record(tokens_in=100, tokens_out=50, model="claude-sonnet")
    assert len(fake.scores) == 1
    s = fake.scores[0]
    assert s["name"] == "claude_tokens_used_pct_month"
    # used_pct = (100 + 50) / 1000 = 0.15
    assert s["value"] == pytest.approx(0.15, abs=1e-9)
    assert "month=" in s["comment"]


def test_promise_v5_no_score_when_langfuse_disabled(monkeypatch, _ledger):
    """Disabled LangFuse → record() still succeeds and emits no scores."""
    fake = _FakeLangfuse()
    from app.observability import langfuse_client as lf

    monkeypatch.setattr(lf, "is_enabled", lambda: False)
    monkeypatch.setattr(lf, "get_langfuse", lambda: fake)
    s = quota_monitor.record(tokens_in=10, tokens_out=5, model="claude-haiku")
    assert s.used_tokens == 15
    assert fake.scores == []


def test_promise_v5_score_emit_failure_does_not_break_gate(monkeypatch, _ledger):
    """A buggy LangFuse SDK must never break record() — observability
    failures are swallowed so the quota gate stays operational."""

    class _Broken:
        def score(self, **_kwargs):
            raise RuntimeError("langfuse offline")

    from app.observability import langfuse_client as lf

    monkeypatch.setattr(lf, "is_enabled", lambda: True)
    monkeypatch.setattr(lf, "get_langfuse", lambda: _Broken())
    # Should NOT raise.
    s = quota_monitor.record(tokens_in=1, tokens_out=1, model="claude-haiku")
    assert s.used_tokens == 2
