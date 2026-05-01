"""Anthropic provider MCP tool'ları — Haiku / Sonnet / Opus."""

from __future__ import annotations

from typing import List

from app.cascade.orchestrator import call_with_cascade
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


async def _anthropic_call(tool_name: str, prompt: str, model: str) -> str:
    await tracker.bump(tool_name)
    try:
        resp = await call_with_cascade(
            prompt,
            primary="anthropic",
            model=model,
            fallbacks=(),
            use_cache=True,
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] {tool_name}: {exc.message}"


@mcp_server.tool()
async def ask_haiku(prompt: str) -> str:
    """Claude Haiku 4.5 — Anthropic'in hızlı modeli. Kısa görev, sınıflandırma."""
    return await _anthropic_call("ask_haiku", prompt, "claude-haiku-4-5-20251001")


@mcp_server.tool()
async def ask_sonnet(prompt: str) -> str:
    """Claude Sonnet 4.6 — dengeli kalite/hız. Kod + analiz için default."""
    return await _anthropic_call("ask_sonnet", prompt, "claude-sonnet-4-6")


@mcp_server.tool()
async def ask_opus(prompt: str) -> str:
    """Claude Opus 4.7 — Anthropic'in en güçlü modeli. Derin analiz, kritik görev."""
    return await _anthropic_call("ask_opus", prompt, "claude-opus-4-7")


REGISTERED_TOOLS.extend(["ask_haiku", "ask_sonnet", "ask_opus"])
