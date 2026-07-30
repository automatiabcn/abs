# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The scheduler that makes a saved cron actually fire.

Before this, the ontology validated a cron trigger and nothing ran it, so a
saved "every Monday at 09:00" was decoration. These tests pin the three things
that make a scheduler trustworthy: it fires when due, it fires ONCE, and a
schedule it cannot read is disabled with the reason rather than retried forever.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from app.workflow_v10 import cron, schedule


# --- the cron grammar -------------------------------------------------------


def test_cron_parses_the_shapes_people_write():
    assert sorted(cron.parse("*/15 * * * *").minute) == [0, 15, 30, 45]
    assert sorted(cron.parse("0 9 * * 1-5").weekday) == [1, 2, 3, 4, 5]
    assert sorted(cron.parse("0 0,12 * * *").hour) == [0, 12]


@pytest.mark.parametrize(
    "expr,reason",
    [
        ("0 9 * *", "5 fields"),
        ("0 99 * * *", "out of range"),
        ("0 9 * * abc", "bad value"),
        ("*/0 * * * *", "step must be positive"),
    ],
)
def test_an_unrunnable_expression_is_refused_with_its_reason(expr, reason):
    with pytest.raises(cron.CronError) as exc:
        cron.parse(expr)
    assert reason in str(exc.value)


def test_matching_uses_cron_weekday_numbering():
    spec = cron.parse("0 9 * * 1")  # Monday in cron
    assert cron.matches(spec, datetime(2026, 8, 3, 9, 0))  # a Monday
    assert not cron.matches(spec, datetime(2026, 8, 4, 9, 0))  # Tuesday


def test_day_of_month_and_weekday_are_or_ed_when_both_restricted():
    # Every cron does this, and it is what "0 9 1,15 * 1" is written to mean.
    spec = cron.parse("0 9 1,15 * 1")
    assert cron.matches(spec, datetime(2026, 8, 3, 9, 0))  # Monday
    assert cron.matches(spec, datetime(2026, 8, 15, 9, 0))  # the 15th
    assert not cron.matches(spec, datetime(2026, 8, 4, 9, 0))


def test_next_after_is_strictly_later():
    spec = cron.parse("0 9 * * *")
    now = datetime(2026, 7, 30, 9, 0)
    assert cron.next_after(spec, now) == datetime(2026, 7, 31, 9, 0)


# --- the schedule itself ----------------------------------------------------


def _saved_workflow(tenant: str, name: str = "digest") -> int:
    from sqlmodel import Session

    from app.db.models import SavedWorkflow
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        row = SavedWorkflow(
            tenant_slug=tenant,
            name=name,
            definition_json=json.dumps({"nodes": [{"id": "t", "kind": "trigger"}]}),
            created_by="alice",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)


def test_setting_a_schedule_computes_the_next_run(tmp_path):
    wf = _saved_workflow("sched-a")
    row = schedule.set_schedule(
        tenant_slug="sched-a", workflow_id=wf, cron_expr="*/5 * * * *", created_by="alice"
    )
    assert row["enabled"] is True
    assert row["next_run_at"] is not None
    assert row["cron_expr"] == "*/5 * * * *"
    assert "reads_as" in row


def test_a_schedule_cannot_be_attached_to_another_tenants_workflow():
    wf = _saved_workflow("owner-corp")
    with pytest.raises(LookupError):
        schedule.set_schedule(
            tenant_slug="intruder-corp", workflow_id=wf, cron_expr="0 9 * * *",
            created_by="mallory",
        )


def test_an_unrunnable_cron_is_refused_at_the_door():
    wf = _saved_workflow("sched-b")
    with pytest.raises(cron.CronError):
        schedule.set_schedule(
            tenant_slug="sched-b", workflow_id=wf, cron_expr="nonsense", created_by="a"
        )


def test_a_due_schedule_runs_once_even_if_two_ticks_race(monkeypatch):
    """Two replicas ticking in the same second must not run one schedule twice —
    the claim moves next_run_at forward in the statement that selects it."""
    wf = _saved_workflow("sched-c")
    schedule.set_schedule(
        tenant_slug="sched-c", workflow_id=wf, cron_expr="* * * * *", created_by="alice"
    )
    started = []

    async def _fake_enqueue(definition, tenant_slug="default"):
        started.append(tenant_slug)
        return f"job-{len(started)}"

    monkeypatch.setattr("app.workflow_v10.runner.enqueue", _fake_enqueue)

    later = datetime.utcnow() + timedelta(minutes=5)
    first = asyncio.run(schedule.tick(later))
    second = asyncio.run(schedule.tick(later))

    assert len(first) == 1, "the due schedule must run"
    assert second == [], "the same due moment must not run it again"
    assert started == ["sched-c"]


def test_a_schedule_whose_workflow_was_deleted_disables_itself(monkeypatch):
    from sqlmodel import Session

    from app.db.models import SavedWorkflow
    from app.db.session import get_engine

    wf = _saved_workflow("sched-d")
    schedule.set_schedule(
        tenant_slug="sched-d", workflow_id=wf, cron_expr="* * * * *", created_by="alice"
    )
    with Session(get_engine()) as db:
        db.delete(db.get(SavedWorkflow, wf))
        db.commit()

    asyncio.run(schedule.tick(datetime.utcnow() + timedelta(minutes=5)))
    rows = schedule.list_schedules(tenant_slug="sched-d")
    assert rows[0]["enabled"] is False
    assert "deleted" in (rows[0]["last_error"] or "")


def test_scheduled_workflow_ids_tells_a_real_schedule_from_a_cron_trigger():
    wf = _saved_workflow("sched-e")
    assert schedule.scheduled_workflow_ids(tenant_slug="sched-e") == set()
    schedule.set_schedule(
        tenant_slug="sched-e", workflow_id=wf, cron_expr="0 9 * * *", created_by="a"
    )
    assert schedule.scheduled_workflow_ids(tenant_slug="sched-e") == {wf}


def test_a_scheduled_job_is_visible_to_the_operator(monkeypatch):
    """The scheduler stamps a job with the tenant; the panel used to ask with an
    email and got job_not_found — the operator could not see what their own
    schedule did. One notion of owner across definitions, schedules and jobs."""
    from app.api.workflows import _job_owner_matches

    admin = {"sub": "admin@local"}
    # A job the scheduler enqueued, keyed by the tenant.
    assert _job_owner_matches({"tenant_slug": "default"}, admin) is True
    # A job enqueued before the change, keyed by the email, still readable.
    assert _job_owner_matches({"tenant_slug": "admin@local"}, admin) is True
    # Another tenant's job stays invisible.
    assert _job_owner_matches({"tenant_slug": "other-corp"}, admin) is False
