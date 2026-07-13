"""T-026 — Recall.ai bot wrapper tests."""

from __future__ import annotations

import pytest

from app.config import settings
from app.meeting import bot_recall as br


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "recall_backend", "mock", raising=False)
    monkeypatch.setattr(settings, "recall_ai_cost_cap_usd_per_day", 50.0, raising=False)
    br.close_bot()
    yield
    br.close_bot()


def test_schedule_returns_job_with_cost_estimate() -> None:
    bot = br.MeetingBot("mock")
    job = bot.schedule(
        meeting_url="https://zoom.us/j/123",
        tenant_id="t1",
        duration_minutes=30,
    )
    assert job.bot_id
    assert job.tenant_id == "t1"
    assert abs(job.estimated_cost_usd - 0.25) < 1e-6


def test_schedule_budget_guard_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "recall_ai_cost_cap_usd_per_day", 0.10, raising=False)
    bot = br.MeetingBot("mock")
    with pytest.raises(br.RecallBudgetExceeded):
        bot.schedule(
            meeting_url="https://zoom.us/j/x",
            tenant_id="t1",
            duration_minutes=30,
        )


def test_status_unknown_id_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        br.MeetingBot("mock").status("nope")


def test_recall_backend_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "recall_ai_api_key", "", raising=False)
    with pytest.raises(ValueError):
        br.MeetingBot("recall")


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        br.MeetingBot("nope")


def test_singleton_lifecycle() -> None:
    a = br.get_bot()
    b = br.get_bot()
    assert a is b
    br.close_bot()
    c = br.get_bot()
    assert c is not a


def test_cancel_removes_job() -> None:
    bot = br.MeetingBot("mock")
    job = bot.schedule(
        meeting_url="https://meet.google.com/abc",
        tenant_id="t1",
        duration_minutes=15,
    )
    bot.cancel(job.bot_id)
    with pytest.raises(KeyError):
        bot.status(job.bot_id)
