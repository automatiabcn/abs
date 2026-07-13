# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Setup wizard step drop-off metrics."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from app.db.models import WizardEvent
from app.db.session import get_session_sync


def record_step(session_id: str, step_num: int, completed: bool = False) -> WizardEvent:
    """Record a step start or completion.

    One row per (session_id, step_num): re-entering a step does not restart it,
    and a completion only ever stamps the first completion time.
    """
    with get_session_sync() as db:
        existing = db.scalars(
            select(WizardEvent)
            .where(WizardEvent.session_id == session_id)
            .where(WizardEvent.step_num == step_num)
        ).first()

        if existing is None:
            row = WizardEvent(session_id=session_id, step_num=step_num)
            if completed:
                row.completed_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

        if completed and existing.completed_at is None:
            existing.completed_at = datetime.now(timezone.utc)
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return existing


def funnel_summary(steps: int = 6) -> dict:
    """Per step: started_count, completed_count, drop_off_pct.

    drop_off_pct = (started - completed) / started x 100.
    """
    out: list[dict] = []
    with get_session_sync() as db:
        for n in range(1, steps + 1):
            rows = db.scalars(
                select(WizardEvent).where(WizardEvent.step_num == n)
            ).all()
            started = len(rows)
            completed = sum(1 for r in rows if r.completed_at is not None)
            drop_off_pct = (
                round(((started - completed) / started) * 100, 1) if started else 0.0
            )
            out.append(
                {
                    "step_num": n,
                    "started": started,
                    "completed": completed,
                    "drop_off_pct": drop_off_pct,
                }
            )

    sessions: set[str] = set()
    final_completed: int = 0
    with get_session_sync() as db:
        all_rows = db.scalars(select(WizardEvent)).all()
        for r in all_rows:
            sessions.add(r.session_id)
            if r.step_num == steps and r.completed_at is not None:
                final_completed += 1

    return {
        "steps": out,
        "total_sessions": len(sessions),
        "final_completed": final_completed,
        "completion_rate_pct": (
            round((final_completed / len(sessions)) * 100, 1) if sessions else 0.0
        ),
    }
