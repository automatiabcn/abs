"""Wizard funnel metric + MCP tool."""

from __future__ import annotations

import asyncio
import json

from sqlmodel import Session, select

from app.db.models import WizardEvent
from app.db.session import get_engine
from app.wizard.metrics import funnel_summary, record_step


def _purge():
    with Session(get_engine()) as s:
        rows = s.scalars(select(WizardEvent)).all()
        for r in rows:
            s.delete(r)
        s.commit()


def test_record_step_inserts_event():
    _purge()
    record_step("session-A", 1, completed=True)
    record_step("session-A", 2, completed=False)

    with Session(get_engine()) as s:
        rows = s.scalars(select(WizardEvent)).all()
        assert len(rows) == 2
        kinds = {(r.step_num, r.completed_at is not None) for r in rows}
        assert (1, True) in kinds
        assert (2, False) in kinds


def test_funnel_summary_drop_off_calc():
    _purge()
    for n in range(1, 7):
        record_step("sessA", n, completed=True)
    for n in range(1, 4):
        record_step("sessB", n, completed=(n < 3))

    summary = funnel_summary(steps=6)
    steps = summary["steps"]
    s1 = next(s for s in steps if s["step_num"] == 1)
    assert s1["started"] == 2
    assert s1["completed"] == 2
    s3 = next(s for s in steps if s["step_num"] == 3)
    assert s3["started"] == 2
    assert s3["completed"] == 1
    s4 = next(s for s in steps if s["step_num"] == 4)
    assert s4["started"] == 1
    assert s4["completed"] == 1
    assert summary["total_sessions"] == 2
    assert summary["final_completed"] == 1


def test_wizard_funnel_mcp_tool_response_shape():
    _purge()
    record_step("sessZ", 1, completed=True)
    record_step("sessZ", 2, completed=False)

    from app.mcp.tools.wizard_tools import wizard_funnel

    raw = asyncio.run(wizard_funnel())
    out = json.loads(raw)
    assert "steps" in out
    assert len(out["steps"]) == 6
    assert "total_sessions" in out
    assert "completion_rate_pct" in out
