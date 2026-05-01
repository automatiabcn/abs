"""010 — Judge persona live training MCP tools (3 tool)."""

from __future__ import annotations

import json
from typing import List

from app.judge.training import persona_status, reset_persona, train_persona
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("judge_persona_status")
async def judge_persona_status() -> str:
    """Mevcut persona threshold'ları + son training meta + history boyutu."""
    await tracker.bump("judge_persona_status")
    return json.dumps(persona_status(), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_persona_train")
async def judge_persona_train(min_samples: int = 10) -> str:
    """judge_log outcome'larından persona dynamic adjust. min_samples altında 'insufficient_data'."""
    await tracker.bump("judge_persona_train")
    return json.dumps(train_persona(min_samples=min_samples), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_persona_reset")
async def judge_persona_reset() -> str:
    """Persona'yı DEFAULT_PERSONA'ya geri al (history dosyası korunur)."""
    await tracker.bump("judge_persona_reset")
    return json.dumps(reset_persona(), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(
    [
        "judge_persona_status",
        "judge_persona_train",
        "judge_persona_reset",
    ]
)
