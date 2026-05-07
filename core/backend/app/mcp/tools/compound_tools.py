# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""030 Modul D — Groq compound (agentic) MCP tools.

`groq/compound` and `groq/compound-mini` are Groq's tool-calling agentic
models. Multi-step reasoning + tool use. Free quota tracked under the
shared Groq tier.
"""

from __future__ import annotations

from typing import List

REGISTERED_TOOLS: List[str] = []

from app.cascade.orchestrator import call_with_cascade  # noqa: E402
from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402
from app.providers.schemas import ProviderError  # noqa: E402


async def _call_groq(
    *, tool_name: str, prompt: str, model: str, max_tokens: int
) -> str:
    await tracker.bump(tool_name)
    try:
        resp = await call_with_cascade(
            prompt,
            primary="groq",
            model=model,
            max_tokens=max_tokens,
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] {tool_name}: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_compound")
async def ask_compound(prompt: str, max_tokens: int = 2000) -> str:
    """Groq Compound — multi-step agentic (planning + tool calling)."""
    return await _call_groq(
        tool_name="ask_compound",
        prompt=prompt,
        model="groq/compound",
        max_tokens=max_tokens,
    )


@mcp_server.tool()
@with_hooks("ask_compound_mini")
async def ask_compound_mini(prompt: str, max_tokens: int = 1000) -> str:
    """Groq Compound Mini — fast agentic (short multi-step tasks)."""
    return await _call_groq(
        tool_name="ask_compound_mini",
        prompt=prompt,
        model="groq/compound-mini",
        max_tokens=max_tokens,
    )


REGISTERED_TOOLS.extend(["ask_compound", "ask_compound_mini"])
