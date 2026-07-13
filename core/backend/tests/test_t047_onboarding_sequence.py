"""T-047 — Onboarding sequence tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.onboarding_v10.sequence import (
    OnboardingScheduler,
    build_onboarding_plan,
)


def _plan(jti: str = "lic-1"):
    return build_onboarding_plan(
        license_jti=jti,
        customer_email=f"{jti}@x.y",
        tenant_id="t1",
        issued_at=datetime(2026, 4, 28, 0, 0, tzinfo=timezone.utc),
    )


def test_plan_includes_all_default_kinds() -> None:
    plan = _plan()
    kinds = {k for k, _ in plan.schedule}
    assert kinds == {"welcome", "walkthrough", "first_success", "expiry_warning"}


def test_plan_orders_by_when() -> None:
    plan = _plan()
    whens = [w for _, w in plan.schedule]
    assert whens == sorted(whens)


def test_plan_validates_required_fields() -> None:
    with pytest.raises(ValueError):
        build_onboarding_plan(
            license_jti="",
            customer_email="x@y.z",
            tenant_id="t1",
        )


def test_due_emits_only_past_kinds() -> None:
    plan = _plan()
    sched = OnboardingScheduler()
    sched.register(plan)
    due = sched.due(now=datetime(2026, 4, 28, 1, 0, tzinfo=timezone.utc))
    kinds = {k for _, k in due}
    assert kinds == {"welcome"}


def test_due_emits_all_after_long_window() -> None:
    plan = _plan()
    sched = OnboardingScheduler()
    sched.register(plan)
    far = datetime(2027, 4, 28, 0, 0, tzinfo=timezone.utc)
    due = sched.due(now=far)
    assert len(due) == 4


def test_mark_sent_is_idempotent() -> None:
    plan = _plan()
    sched = OnboardingScheduler()
    sched.register(plan)
    assert sched.mark_sent(license_jti=plan.license_jti, kind="welcome") is True
    assert sched.mark_sent(license_jti=plan.license_jti, kind="welcome") is False


def test_cancel_removes_plan() -> None:
    plan = _plan()
    sched = OnboardingScheduler()
    sched.register(plan)
    assert sched.cancel(license_jti=plan.license_jti) is True
    assert sched.cancel(license_jti=plan.license_jti) is False


def test_register_duplicate_raises() -> None:
    plan = _plan()
    sched = OnboardingScheduler()
    sched.register(plan)
    with pytest.raises(ValueError):
        sched.register(plan)


def test_mark_sent_unknown_jti_raises() -> None:
    sched = OnboardingScheduler()
    with pytest.raises(KeyError):
        sched.mark_sent(license_jti="nope", kind="welcome")
