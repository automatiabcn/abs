# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Where an agent's consequential tool call becomes something a person can say
no to.

Until now the loop announced "this needs approval" into the stream and stopped.
That was honest but useless: there was nothing to approve, and the write never
happened even if the operator wanted it to. This turns the intent into a row in
the Approval Center — the same queue, the same decide endpoint, the same
once-only execution guard the outbound agents already use — so the assistant can
propose a write and the person can accept it, in one place, with a record.

The call is stored as data (tool name + arguments), never as a resolved action.
It is re-checked against the policy gate at execution time, not at proposal time:
an operator who switches shell off after the model asked for it has switched it
off, and an approval minted while the door was open is not a key to it.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.db.models import ApprovalItem
from app.db.session import get_engine

logger = logging.getLogger(__name__)

# The channel that tells the Approval Center's executor "this is an agent tool
# call, not a message to a customer".
AGENT_TOOL_CHANNEL = "agent_tool"

# The risk the panel shows. Running a command is not the same as saving a note,
# and an operator scanning a queue should be able to see which is which without
# reading the arguments.
_RISK_BY_TOOL = {"run_command": "high", "fs_write": "medium"}


def payload_of(item: Any) -> Optional[Dict[str, Any]]:
    """The (tool, args) an approval carries, or None if it is not a tool call."""
    if (getattr(item, "channel", "") or "").strip() != AGENT_TOOL_CHANNEL:
        return None
    try:
        data = json.loads(getattr(item, "proposed_message", "") or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    args = data.get("args")
    return {"name": data["name"], "args": args if isinstance(args, dict) else {}}


def _describe(name: str, args: Dict[str, Any]) -> str:
    """What the operator reads in the queue, in their own terms."""
    if name == "run_command":
        return f"Run a command on the server: {args.get('command', '')}"[:1024]
    if name == "fs_write":
        content = str(args.get("content") or "")
        return (
            f"Write {len(content)} characters to {args.get('path', '')}"
        )[:1024]
    return f"Run the tool '{name}'"[:1024]


def request_tool_approval(
    *,
    name: str,
    args: Dict[str, Any],
    tenant_slug: str,
    requester: str,
    rationale: str = "",
) -> Dict[str, Any]:
    """Open a pending approval for a tool call the assistant wants to make."""
    row = ApprovalItem(
        tenant_slug=tenant_slug or "default",
        agent_id="assistant",
        action=_describe(name, args),
        channel=AGENT_TOOL_CHANNEL,
        # Who was talking to the assistant when it asked. The queue is read by a
        # person deciding whether this was a reasonable thing to want.
        target_person=(requester or "")[:256],
        rationale=(rationale or "The assistant asked to do this while answering a question.")[:4096],
        # The call itself, stored verbatim. The executor runs *this*, not the
        # human-readable summary above — a description drifting from the payload
        # is how someone ends up approving one thing and running another.
        proposed_message=json.dumps({"name": name, "args": args}, ensure_ascii=False)[:8192],
        risk=_RISK_BY_TOOL.get(name, "medium"),
        policy_result="requires_approval",
        status="pending",
    )

    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "agent tool approval opened id=%s tool=%s tenant=%s", row.id, name, tenant_slug
        )
        return {"id": row.id, "action": row.action, "risk": row.risk}
