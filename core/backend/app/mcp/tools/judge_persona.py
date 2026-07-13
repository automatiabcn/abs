# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Judge persona live-training MCP tools — status, train, reset."""

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
    """Current persona thresholds, last training run, and history size."""
    await tracker.bump("judge_persona_status")
    return json.dumps(persona_status(), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_persona_train")
async def judge_persona_train(min_samples: int = 10) -> str:
    """Retune the persona from recorded judge outcomes. Below min_samples it
    refuses with 'insufficient_data' rather than fitting to noise."""
    await tracker.bump("judge_persona_train")
    return json.dumps(train_persona(min_samples=min_samples), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_persona_reset")
async def judge_persona_reset() -> str:
    """Reset the persona to its defaults. The outcome history is kept, so a
    later train() can rebuild from the same evidence."""
    await tracker.bump("judge_persona_reset")
    return json.dumps(reset_persona(), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(
    [
        "judge_persona_status",
        "judge_persona_train",
        "judge_persona_reset",
    ]
)
