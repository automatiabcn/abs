# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Weekly status report aggregator.

Pulls Linear closed tickets, GitHub merged PRs, Slack highlights, and logged
hours via injected callables. Outputs a structured `StatusReport` ready for
LLM summarisation + email send. The cron schedule (Friday 17:00) lives in the
n8n workflow JSON.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = ["StatusReport", "ProjectActivity", "build_status_report"]


@dataclass(slots=True)
class ProjectActivity:
    project_id: str
    project_name: str
    closed_tickets: list[str]
    merged_prs: list[str]
    slack_highlights: list[str]
    logged_hours: float = 0.0


@dataclass(slots=True)
class StatusReport:
    tenant_id: str
    week_starts_at: str
    week_ends_at: str
    activities: list[ProjectActivity] = field(default_factory=list)

    def total_hours(self) -> float:
        return sum(a.logged_hours for a in self.activities)


def _week_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    end = reference or datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    return start, end


def build_status_report(
    *,
    tenant_id: str,
    project_ids: list[str],
    linear_closed: Callable[[str, datetime, datetime], list[str]],
    github_merged: Callable[[str, datetime, datetime], list[str]],
    slack_highlights: Callable[[str, datetime, datetime], list[str]],
    hours_logged: Callable[[str, datetime, datetime], float],
    reference: datetime | None = None,
    project_name_lookup: Callable[[str], str] | None = None,
) -> StatusReport:
    if not tenant_id:
        raise ValueError("tenant_id required")
    start, end = _week_window(reference)
    activities: list[ProjectActivity] = []
    for pid in project_ids:
        activities.append(
            ProjectActivity(
                project_id=pid,
                project_name=(project_name_lookup or (lambda x: x))(pid),
                closed_tickets=linear_closed(pid, start, end),
                merged_prs=github_merged(pid, start, end),
                slack_highlights=slack_highlights(pid, start, end),
                logged_hours=float(hours_logged(pid, start, end) or 0.0),
            )
        )
    report = StatusReport(
        tenant_id=tenant_id,
        week_starts_at=start.isoformat(timespec="seconds"),
        week_ends_at=end.isoformat(timespec="seconds"),
        activities=activities,
    )
    logger.info(
        "status_report tenant=%s projects=%d hours=%.1f",
        tenant_id,
        len(activities),
        report.total_hours(),
    )
    return report
