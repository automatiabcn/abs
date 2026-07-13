"""plan_first — action_count >= 3 + plan.md yok → uyarı."""

from __future__ import annotations


import pytest

from app.config import settings
from app.hooks import plan_first


@pytest.fixture
def _artifact_task(tmp_path, monkeypatch):
    task_dir = tmp_path / "20260424_123_task-x"
    task_dir.mkdir()
    (task_dir / "action_count.txt").write_text("5")
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path / "cache"))
    return task_dir


def test_warns_when_action_count_high_and_no_plan(_artifact_task):
    msg = plan_first.maybe_plan_first_nudge()
    assert "PLAN-FIRST" in msg
    assert "plan.md" in msg


def test_silent_when_plan_exists(_artifact_task):
    (_artifact_task / "plan.md").write_text("# plan")
    msg = plan_first.maybe_plan_first_nudge()
    assert msg == ""


def test_rate_limit_suppresses_second_warning(_artifact_task):
    first = plan_first.maybe_plan_first_nudge()
    second = plan_first.maybe_plan_first_nudge()
    assert first != ""
    assert second == ""


def test_silent_when_no_artifact_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path / "nope"))
    msg = plan_first.maybe_plan_first_nudge()
    assert msg == ""
