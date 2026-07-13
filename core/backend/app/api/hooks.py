# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""HTTP endpoint backing the native hook integration.

The installed hook script (~/.claude/hooks/pre-tool-guard.sh) pipes the event
JSON it receives on stdin to this endpoint and writes the response back to
stdout, so the request body is a Claude Code PreToolUse event:

  {
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "..."}
  }

The response conforms to the Claude Code hook JSON output spec.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# Reuse the same bearer+scope gate the sibling /v1/hooks/* endpoints use.
# /dispatch + /test run the hook dispatcher and were previously UNAUTHENTICATED
# while reachable through Caddy (@backend path /v1/*) — any caller could drive
# the hook engine. Gate them like quota-check/audit-log/session-start.
from app.api.claude_code_hooks import _auth_dependency
from app.hooks.dispatcher import dispatch_hooks, to_claude_code_hook_output

router = APIRouter(
    prefix="/v1/hooks",
    tags=["hooks"],
    dependencies=[Depends(_auth_dependency)],
)


class HookRequest(BaseModel):
    hook_event_name: str = Field(default="PreToolUse")
    tool_name: str = Field(..., min_length=1, max_length=128)
    tool_input: dict = Field(default_factory=dict)


@router.post("/dispatch")
async def dispatch(req: HookRequest) -> dict:
    result = dispatch_hooks(req.tool_name, req.tool_input)
    return to_claude_code_hook_output(result)


@router.post("/test")
async def test_dispatch(req: HookRequest) -> dict:
    """Debug variant of /dispatch: returns the raw dispatcher result (including
    the deny reason) instead of the hook output spec."""
    return dispatch_hooks(req.tool_name, req.tool_input)
