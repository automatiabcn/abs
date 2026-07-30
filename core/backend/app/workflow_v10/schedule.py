# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Workflow schedules — the thing that makes a saved cron actually fire.

Until now the product could DESCRIBE a schedule (the ontology validates a cron
trigger) and nothing ran it, so a saved "every Monday at 09:00" was decoration.
This is the missing half: a row per schedule, a tick that claims what is due,
and a run that goes through the normal workflow runner — which pins LLM steps
to the free tier, so a schedule firing at 3am cannot spend money unattended.

Claiming is atomic on ``next_run_at``: two replicas ticking at the same second
must not run the same schedule twice.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.db.models import SavedWorkflow, WorkflowSchedule
from app.db.session import get_engine
from app.workflow_v10 import cron

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """UTC-naive, matching how the rest of this codebase stores time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(row: WorkflowSchedule, workflow_name: str = "") -> Dict[str, Any]:
    reading = ""
    try:
        reading = cron.describe(cron.parse(row.cron_expr))
    except cron.CronError:
        reading = "unreadable schedule"
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "workflow_name": workflow_name,
        "cron_expr": row.cron_expr,
        "reads_as": reading,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "last_job_id": row.last_job_id,
        "last_error": row.last_error,
        "created_by": row.created_by,
    }


def set_schedule(
    *, tenant_slug: str, workflow_id: int, cron_expr: str, created_by: str
) -> Dict[str, Any]:
    """Create or replace the schedule for one workflow. Raises CronError when
    the expression is not one this scheduler can run — better a refusal at the
    door than a schedule that silently never fires."""
    spec = cron.parse(cron_expr)
    now = _now()
    upcoming = cron.next_after(spec, now)
    if upcoming is None:
        raise cron.CronError(
            f"{cron_expr} has no occurrence within a year — nothing would ever run"
        )

    with Session(get_engine()) as db:
        workflow = db.get(SavedWorkflow, workflow_id)
        if workflow is None or workflow.tenant_slug != tenant_slug:
            raise LookupError("workflow_not_found")
        row = db.exec(
            select(WorkflowSchedule).where(
                WorkflowSchedule.tenant_slug == tenant_slug,
                WorkflowSchedule.workflow_id == workflow_id,
            )
        ).first()
        if row is None:
            row = WorkflowSchedule(
                tenant_slug=tenant_slug,
                workflow_id=workflow_id,
                cron_expr=spec.expression,
                enabled=True,
                next_run_at=upcoming,
                created_by=created_by,
                created_at=now,
            )
        else:
            row.cron_expr = spec.expression
            row.enabled = True
            row.next_run_at = upcoming
            row.last_error = None
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize(row, workflow.name)


def delete_schedule(*, tenant_slug: str, schedule_id: int) -> bool:
    with Session(get_engine()) as db:
        row = db.get(WorkflowSchedule, schedule_id)
        if row is None or row.tenant_slug != tenant_slug:
            return False
        db.delete(row)
        db.commit()
    return True


def list_schedules(*, tenant_slug: str) -> List[Dict[str, Any]]:
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(WorkflowSchedule).where(
                    WorkflowSchedule.tenant_slug == tenant_slug
                )
            )
        )
        names = {
            w.id: w.name
            for w in db.exec(
                select(SavedWorkflow).where(SavedWorkflow.tenant_slug == tenant_slug)
            )
        }
    return [_serialize(r, names.get(r.workflow_id, "")) for r in rows]


def scheduled_workflow_ids(*, tenant_slug: str) -> set:
    """Which workflows actually have a live schedule — so a panel can tell a
    real schedule from a cron trigger nobody runs."""
    with Session(get_engine()) as db:
        rows = db.exec(
            select(WorkflowSchedule).where(
                WorkflowSchedule.tenant_slug == tenant_slug,
                WorkflowSchedule.enabled == True,  # noqa: E712 — SQL, not Python
            )
        ).all()
    return {r.workflow_id for r in rows}


def _claim_due(now: datetime) -> List[Dict[str, Any]]:
    """Atomically take the schedules that are due.

    The claim moves ``next_run_at`` forward in the same statement that selects
    the row, so a second ticker (another replica, or a restart overlapping the
    old process) finds nothing to do rather than running the workflow twice.
    """
    # Plain dicts, not ORM rows: the session closes before the caller runs the
    # workflow, and a detached row cannot be read.
    claimed: List[Dict[str, Any]] = []
    with Session(get_engine()) as db:
        due = list(
            db.exec(
                select(WorkflowSchedule)
                .where(WorkflowSchedule.enabled == True)  # noqa: E712
                .where(WorkflowSchedule.next_run_at <= now)
            )
        )
        for row in due:
            try:
                spec = cron.parse(row.cron_expr)
                upcoming = cron.next_after(spec, now)
            except cron.CronError as exc:
                # An unreadable expression disables the schedule with the reason
                # recorded, instead of retrying it every tick forever.
                db.execute(
                    sa_update(WorkflowSchedule)
                    .where(WorkflowSchedule.id == row.id)
                    .values(enabled=False, last_error=f"cron: {exc}")
                )
                db.commit()
                continue
            result = db.execute(
                sa_update(WorkflowSchedule)
                .where(WorkflowSchedule.id == row.id)
                .where(WorkflowSchedule.next_run_at <= now)
                .values(next_run_at=upcoming, last_run_at=now)
            )
            db.commit()
            if (result.rowcount or 0) == 1:
                claimed.append(
                    {
                        "id": row.id,
                        "workflow_id": row.workflow_id,
                        "tenant_slug": row.tenant_slug,
                    }
                )
    return claimed


async def tick(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """One scheduler pass: claim what is due and enqueue it. Returns what ran."""
    from app.workflow_v10 import runner

    moment = now or _now()
    ran: List[Dict[str, Any]] = []
    for row in _claim_due(moment):
        with Session(get_engine()) as db:
            workflow = db.get(SavedWorkflow, row["workflow_id"])
        if workflow is None:
            with Session(get_engine()) as db:
                db.execute(
                    sa_update(WorkflowSchedule)
                    .where(WorkflowSchedule.id == row["id"])
                    .values(enabled=False, last_error="workflow was deleted")
                )
                db.commit()
            continue
        try:
            definition = json.loads(workflow.definition_json)
            job_id = await runner.enqueue(definition, tenant_slug=row["tenant_slug"])
            error = None
        except Exception as exc:  # noqa: BLE001 — one bad schedule must not stop the rest
            job_id = ""
            error = str(exc)[:300]
            logger.warning("scheduled workflow %s failed to start: %s", workflow.name, exc)
        with Session(get_engine()) as db:
            db.execute(
                sa_update(WorkflowSchedule)
                .where(WorkflowSchedule.id == row["id"])
                .values(last_job_id=job_id, last_error=error)
            )
            db.commit()
        ran.append(
            {
                "schedule_id": row["id"],
                "workflow": workflow.name,
                "job_id": job_id,
                "error": error,
            }
        )
    return ran
