# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Upper-tier + auto-upgrade alias MCP tools.

  ask_cerebras_qwen     — Cerebras gpt-oss-120b
  ask_gemini_latest     — gemini-flash-latest (auto-upgrade alias)
  ask_gemini_pro_latest — gemini-pro-latest (auto-upgrade alias)
"""

from __future__ import annotations

from typing import List

REGISTERED_TOOLS: List[str] = []

from app.cascade.orchestrator import call_with_cascade  # noqa: E402
from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402
from app.providers.schemas import ProviderError  # noqa: E402


async def _call(
    *, tool_name: str, prompt: str, primary: str, model: str, max_tokens: int = 2000
) -> str:
    await tracker.bump(tool_name)
    try:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            model=model,
            max_tokens=max_tokens,
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] {tool_name}: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_cerebras_qwen")
async def ask_cerebras_qwen(prompt: str, max_tokens: int = 2000) -> str:
    """Cerebras Qwen3-235B — upper tier (paid plan; graceful skip if no key)."""
    return await _call(
        tool_name="ask_cerebras_qwen",
        prompt=prompt,
        primary="cerebras",
        model="gpt-oss-120b",
        max_tokens=max_tokens,
    )


@mcp_server.tool()
@with_hooks("ask_gemini_latest")
async def ask_gemini_latest(prompt: str) -> str:
    """Gemini Flash Latest — auto-upgrade alias (3.x rolls forward)."""
    return await _call(
        tool_name="ask_gemini_latest",
        prompt=prompt,
        primary="gemini",
        model="gemini-flash-latest",
    )


@mcp_server.tool()
@with_hooks("ask_gemini_pro_latest")
async def ask_gemini_pro_latest(prompt: str) -> str:
    """Gemini Pro Latest — auto-upgrade Pro tier alias."""
    return await _call(
        tool_name="ask_gemini_pro_latest",
        prompt=prompt,
        primary="gemini",
        model="gemini-pro-latest",
    )


REGISTERED_TOOLS.extend(
    ["ask_cerebras_qwen", "ask_gemini_latest", "ask_gemini_pro_latest"]
)
