"""Weekly status report aggregator tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.workflow_v10.status_report import build_status_report


def _stubs(payloads: dict[str, dict]):
    def linear(pid, s, e):  # noqa: ANN001
        return payloads.get(pid, {}).get("linear", [])

    def github(pid, s, e):  # noqa: ANN001
        return payloads.get(pid, {}).get("github", [])

    def slack(pid, s, e):  # noqa: ANN001
        return payloads.get(pid, {}).get("slack", [])

    def hours(pid, s, e):  # noqa: ANN001
        return payloads.get(pid, {}).get("hours", 0.0)

    return linear, github, slack, hours


def test_aggregates_all_projects() -> None:
    linear, github, slack, hours = _stubs(
        {
            "P1": {
                "linear": ["LIN-1", "LIN-2"],
                "github": ["#100"],
                "slack": ["release v0.9"],
                "hours": 12.5,
            },
            "P2": {
                "linear": [],
                "github": ["#101"],
                "slack": [],
                "hours": 4.0,
            },
        }
    )
    report = build_status_report(
        tenant_id="t1",
        project_ids=["P1", "P2"],
        linear_closed=linear,
        github_merged=github,
        slack_highlights=slack,
        hours_logged=hours,
    )
    assert len(report.activities) == 2
    assert report.total_hours() == 16.5
    assert report.activities[0].project_id == "P1"


def test_status_report_requires_tenant() -> None:
    with pytest.raises(ValueError):
        build_status_report(
            tenant_id="",
            project_ids=["P1"],
            linear_closed=lambda *a: [],
            github_merged=lambda *a: [],
            slack_highlights=lambda *a: [],
            hours_logged=lambda *a: 0.0,
        )


def test_status_report_window_uses_reference() -> None:
    ref = datetime(2026, 4, 28, 17, 0, tzinfo=timezone.utc)
    report = build_status_report(
        tenant_id="t1",
        project_ids=["P1"],
        linear_closed=lambda p, s, e: [s.isoformat()],
        github_merged=lambda *a: [],
        slack_highlights=lambda *a: [],
        hours_logged=lambda *a: 0.0,
        reference=ref,
    )
    assert report.week_ends_at.startswith("2026-04-28")
    assert report.week_starts_at.startswith("2026-04-21")


def test_project_name_lookup_used() -> None:
    report = build_status_report(
        tenant_id="t1",
        project_ids=["P1"],
        linear_closed=lambda *a: [],
        github_merged=lambda *a: [],
        slack_highlights=lambda *a: [],
        hours_logged=lambda *a: 0.0,
        project_name_lookup=lambda pid: f"Project-{pid}",
    )
    assert report.activities[0].project_name == "Project-P1"
