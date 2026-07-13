# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The nine baseline provider tools. Each one goes through the cascade, so a
dead primary fails over instead of surfacing as a tool error."""

from __future__ import annotations

from typing import List

from app.cascade.orchestrator import call_with_cascade
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


async def _call(
    *,
    tool_name: str,
    prompt: str,
    primary: str,
    model: str,
    fallbacks: tuple = (),
) -> str:
    """Shared tool body: usage tracking, cascade call, and a provider failure
    returned as text rather than raised — an MCP tool must not throw at a client."""
    await tracker.bump(tool_name)
    try:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            model=model,
            fallbacks=fallbacks,
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] {tool_name}: {exc.message}"


@mcp_server.tool()
async def ask_groq_fast(prompt: str) -> str:
    """Llama 3.1 8B (Groq) — ultra fast (<0.3s). Short questions, classification."""
    return await _call(
        tool_name="ask_groq_fast",
        prompt=prompt,
        primary="groq",
        model="llama-3.1-8b-instant",
        fallbacks=("cerebras",),
    )


@mcp_server.tool()
@with_hooks("ask_scout")
async def ask_scout(prompt: str) -> str:
    """Llama 4 Scout 17B (Groq) — instruction following, short tasks."""
    return await _call(
        tool_name="ask_scout",
        prompt=prompt,
        primary="groq",
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        fallbacks=("cloudflare",),
    )


@mcp_server.tool()
async def ask_cerebras(prompt: str) -> str:
    """Cerebras — 235B MoE, ~0.3s latency, 1M tokens/day on the free tier."""
    return await _call(
        tool_name="ask_cerebras",
        prompt=prompt,
        primary="cerebras",
        model="gpt-oss-120b",
    )


@mcp_server.tool()
async def ask_gemini(prompt: str) -> str:
    """Gemini 2.5 Flash — fast multimodal. Templates, short generation."""
    return await _call(
        tool_name="ask_gemini",
        prompt=prompt,
        primary="gemini",
        model="gemini-2.5-flash",
    )


@mcp_server.tool()
async def ask_gemini_pro(prompt: str) -> str:
    """Gemini 2.5 Pro — 1M context, deep analysis, multimodal."""
    return await _call(
        tool_name="ask_gemini_pro",
        prompt=prompt,
        primary="gemini",
        model="gemini-2.5-pro",
    )


@mcp_server.tool()
async def ask_cf(prompt: str) -> str:
    """CloudFlare Llama 3.3 70B FP8 Fast — edge latency."""
    return await _call(
        tool_name="ask_cf",
        prompt=prompt,
        primary="cloudflare",
        model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    )


@mcp_server.tool()
async def ask_cf_gptoss(prompt: str) -> str:
    """CloudFlare GPT-OSS 120B — 120B at the edge; alternative to the Groq route."""
    return await _call(
        tool_name="ask_cf_gptoss",
        prompt=prompt,
        primary="cloudflare",
        model="@cf/openai/gpt-oss-120b",
    )


@mcp_server.tool()
async def ask_kimi(prompt: str) -> str:
    """Kimi K2.5 (CloudFlare) — code generation and planning. 256K context."""
    return await _call(
        tool_name="ask_kimi",
        prompt=prompt,
        primary="cloudflare",
        model="@cf/moonshotai/kimi-k2.5",
    )


@mcp_server.tool()
async def ask_phi4(prompt: str) -> str:
    """Phi-4 via local Ollama — reasoning. Requires OLLAMA_URL to be set."""
    return await _call(
        tool_name="ask_phi4",
        prompt=prompt,
        primary="ollama",
        model="phi4",
    )


REGISTERED_TOOLS.extend(
    [
        "ask_groq_fast",
        "ask_scout",
        "ask_cerebras",
        "ask_gemini",
        "ask_gemini_pro",
        "ask_cf",
        "ask_cf_gptoss",
        "ask_kimi",
        "ask_phi4",
    ]
)
