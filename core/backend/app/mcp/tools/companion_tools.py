# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Companion MCP tools — approvals, meetings and workflows for the editor.

The Approval Center and the meeting record are two of the product's own
surfaces, and both were reachable only over ``/v1`` with a panel cookie or an
OAuth JWT. An editor holding an ``abs_mcp_`` token could therefore show neither
— it could propose a risky change and never show the queue that gates it, and
it could index a meeting and never show what was said.

Everything here is tenant-scoped from the CALLER's token, never from an
argument: a tool that took ``tenant_slug`` from its input would let any token
read any tenant's approval queue.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


def _caller() -> tuple[str, str]:
    """(tenant, user) from the MCP token. Falls back to the configured default."""
    try:
        from app.mcp.context import get_mcp_caller

        tenant, user = get_mcp_caller()
        if tenant:
            return str(tenant), str(user or "mcp")
    except Exception:  # pragma: no cover — defensive
        pass
    return (getattr(settings, "mcp_rag_tenant", None) or "default"), "mcp"


# --- Approval Center --------------------------------------------------------


@mcp_server.tool()
@with_hooks("approvals_list")
async def approvals_list(status: str = "pending", limit: int = 50) -> str:
    """The approval queue for this tenant: items plus the risk-bucket summary
    the Approval Center header shows. `status`: pending | approved | rejected |
    all."""
    await tracker.bump("approvals_list")
    from app.approvals import service as _svc

    tenant, _user = _caller()
    try:
        data = _svc.list_approvals(tenant_slug=tenant, status=status, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "approvals_unavailable", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, **data}, ensure_ascii=False, default=str)


@mcp_server.tool()
@with_hooks("approvals_decide")
async def approvals_decide(
    item_id: int, decision: str, note: str = "", edited_message: str = ""
) -> str:
    """Approve, reject or edit one pending approval item. `decision`: approve |
    reject | edit. An item that was already decided is refused, not rewritten."""
    await tracker.bump("approvals_decide")
    from app.approvals import service as _svc

    tenant, user = _caller()
    try:
        row = _svc.decide_approval(
            tenant_slug=tenant,
            item_id=int(item_id),
            decision=decision,
            decided_by=f"editor:{user}",
            note=note,
            edited_message=edited_message,
        )
    except ValueError as exc:
        return json.dumps(
            {"ok": False, "error": "invalid_decision", "detail": str(exc)},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "decide_failed", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    if row is None:
        # Same answer for "not this tenant's item" as for "no such item": the
        # queue of another tenant must not be probeable one id at a time.
        return json.dumps(
            {"ok": False, "error": "not_found_or_not_pending"}, ensure_ascii=False
        )
    return json.dumps({"ok": True, "item": row}, ensure_ascii=False, default=str)


# --- Meetings ---------------------------------------------------------------


@mcp_server.tool()
@with_hooks("meetings_list")
async def meetings_list(limit: int = 20) -> str:
    """Recorded meetings for this tenant, newest first: status, duration,
    speaker count, summary and whether the transcript reached the knowledge
    base."""
    await tracker.bump("meetings_list")
    from sqlmodel import Session, select

    from app.db.models import Meeting
    from app.db.session import get_engine

    tenant, _user = _caller()
    try:
        with Session(get_engine()) as db:
            rows = list(
                db.exec(
                    select(Meeting)
                    .where(Meeting.tenant_slug == tenant)
                    .order_by(Meeting.created_at.desc())  # type: ignore[attr-defined]
                    .limit(max(1, min(int(limit), 100)))
                )
            )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "meetings_unavailable", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )
    items: List[Dict[str, Any]] = [
        {
            "id": m.id,
            "filename": m.filename,
            "duration_sec": m.duration_sec,
            "speaker_count": m.speaker_count,
            "status": m.status,
            "summary": m.summary,
            "indexed": bool(getattr(m, "indexed", False)),
            "created_at": m.created_at,
        }
        for m in rows
    ]
    return json.dumps(
        {"ok": True, "count": len(items), "meetings": items},
        ensure_ascii=False,
        default=str,
    )


@mcp_server.tool()
@with_hooks("meeting_get")
async def meeting_get(meeting_id: int, with_segments: bool = True) -> str:
    """One meeting: summary, speakers, the transcript segments, and the action
    items detected in it — what a task panel turns into work."""
    await tracker.bump("meeting_get")
    from sqlmodel import Session, select

    from app.db.models import Meeting, MeetingSegment
    from app.db.session import get_engine

    tenant, _user = _caller()
    try:
        with Session(get_engine()) as db:
            meeting = db.get(Meeting, int(meeting_id))
            if meeting is None or meeting.tenant_slug != tenant:
                return json.dumps(
                    {"ok": False, "error": "not_found"}, ensure_ascii=False
                )
            segments = (
                list(
                    db.exec(
                        select(MeetingSegment)
                        .where(MeetingSegment.meeting_id == meeting.id)
                        .order_by(MeetingSegment.start_sec)  # type: ignore[attr-defined]
                    )
                )
                if with_segments
                else []
            )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": "meeting_unavailable", "detail": str(exc)[:300]},
            ensure_ascii=False,
        )

    seg_payload = [
        {
            "speaker_id": s.speaker_id,
            "start": s.start_sec,
            "end": s.end_sec,
            "text": s.text,
        }
        for s in segments
    ]
    actions: List[Dict[str, Any]] = []
    if seg_payload:
        try:
            from app.meeting.action_items import extract_action_items
            from app.meeting.transcribe import Transcript, TranscriptSegment

            transcript = Transcript(
                language="",
                duration=float(meeting.duration_sec or 0),
                backend="stored",
                segments=[
                    TranscriptSegment(
                        speaker=s["speaker_id"],
                        start=float(s["start"] or 0),
                        end=float(s["end"] or 0),
                        text=s["text"] or "",
                    )
                    for s in seg_payload
                ],
            )
            actions = [
                {
                    "text": a.text,
                    "assignee": a.assignee,
                    "due_date": a.due_date,
                    "source_segment": a.source_segment,
                }
                for a in extract_action_items(transcript)
            ]
        except Exception:  # noqa: BLE001 — action items are a bonus, not the record
            actions = []

    return json.dumps(
        {
            "ok": True,
            "id": meeting.id,
            "filename": meeting.filename,
            "status": meeting.status,
            "duration_sec": meeting.duration_sec,
            "speaker_count": meeting.speaker_count,
            "summary": meeting.summary,
            "indexed": bool(getattr(meeting, "indexed", False)),
            "created_at": meeting.created_at,
            "segments": seg_payload,
            "action_items": actions,
        },
        ensure_ascii=False,
        default=str,
    )


REGISTERED_TOOLS.extend(
    ["approvals_list", "approvals_decide", "meetings_list", "meeting_get"]
)

__all__ = [
    "approvals_list",
    "approvals_decide",
    "meetings_list",
    "meeting_get",
    "REGISTERED_TOOLS",
]
