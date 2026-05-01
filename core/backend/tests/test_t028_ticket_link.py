"""T-028 — Ticket linking tests."""

from __future__ import annotations

from app.meeting.action_items import ActionItem
from app.meeting.ticket_link import (
    ExistingTicket,
    decide_ticket_action,
    link_action_items,
)


def test_create_when_no_existing_tickets() -> None:
    item = ActionItem(text="Send Q3 report", assignee="Ahmet", due_date=None, source_segment=0)
    d = decide_ticket_action(item, [])
    assert d.action == "create"
    assert d.target_id is None
    assert d.similarity == 0.0


def test_update_when_existing_above_threshold() -> None:
    item = ActionItem(text="Send Q3 report", assignee="Ahmet", due_date=None, source_segment=0)
    existing = [
        ExistingTicket(ticket_id="LIN-1", title="Send Q3 report"),
        ExistingTicket(ticket_id="LIN-2", title="Unrelated documentation"),
    ]
    d = decide_ticket_action(item, existing)
    assert d.action == "update"
    assert d.target_id == "LIN-1"
    assert d.similarity > 0.85


def test_create_when_existing_below_threshold() -> None:
    item = ActionItem(text="ABS RAG documentation", assignee="A", due_date=None, source_segment=0)
    existing = [
        ExistingTicket(ticket_id="LIN-9", title="completely unrelated billing change"),
    ]
    d = decide_ticket_action(item, existing)
    assert d.action == "create"


def test_link_action_items_summary_counts() -> None:
    items = [
        ActionItem(text="Send Q3 report", assignee="A", due_date=None, source_segment=0),
        ActionItem(text="ABS RAG documentation", assignee="B", due_date=None, source_segment=1),
    ]
    existing = [ExistingTicket(ticket_id="LIN-1", title="Send Q3 report")]
    decisions = link_action_items(items, existing)
    assert sum(1 for d in decisions if d.action == "update") == 1
    assert sum(1 for d in decisions if d.action == "create") == 1


def test_decisions_require_human_approval_by_default() -> None:
    item = ActionItem(text="x", assignee="A", due_date=None, source_segment=0)
    d = decide_ticket_action(item, [])
    assert d.requires_human_approval is True
