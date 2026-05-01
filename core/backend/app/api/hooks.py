"""Native hook (Mod A) için HTTP endpoint.

Claude Code ~/.claude/hooks/pre-tool-guard.sh scripti Claude Code'dan gelen
stdin JSON'ını bu endpoint'e POST eder, response stdout'a geri basılır.

İstek formatı (Claude Code PreToolUse event'inden):
  {
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "..."}
  }

Yanıt: Claude Code hook JSON output spec uyumlu.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.hooks.dispatcher import dispatch_hooks, to_claude_code_hook_output

router = APIRouter(prefix="/v1/hooks", tags=["hooks"])


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
    """Dev / test amaçlı — içerik ve deny reason'ı doğrudan görmek için."""
    return dispatch_hooks(req.tool_name, req.tool_input)
