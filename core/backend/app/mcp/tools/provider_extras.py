# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The specialist provider tools — one per model that is good at one thing.

All of them go through the cascade. A missing provider key is returned as an
error string, never raised: an MCP tool must not throw at its client.
"""

from __future__ import annotations

from typing import List

from app.cascade.orchestrator import call_with_cascade
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


async def _call(
    tool_name: str,
    prompt: str,
    primary: str,
    model: str,
    fallbacks: tuple = (),
) -> str:
    await tracker.bump(tool_name)
    try:
        resp = await call_with_cascade(
            prompt, primary=primary, model=model, fallbacks=fallbacks
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] {tool_name}: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_smart")
async def ask_smart(prompt: str) -> str:
    """General-purpose route — gpt-oss-120b, falling back to CF then Cerebras."""
    return await _call(
        "ask_smart",
        prompt,
        primary="groq",
        model="openai/gpt-oss-120b",
        fallbacks=("cloudflare", "cerebras"),
    )


@mcp_server.tool()
@with_hooks("ask_rerank")
async def ask_rerank(prompt: str) -> str:
    """Cohere Command R+ — rerank-capable chat; cache-aware."""
    return await _call(
        "ask_rerank", prompt, primary="cohere", model="command-r-plus-08-2024"
    )


@mcp_server.tool()
@with_hooks("ask_aya")
async def ask_aya(prompt: str) -> str:
    """Aya 8B via local Ollama — grammar and style, strongest on Turkish."""
    return await _call("ask_aya", prompt, primary="ollama", model="aya:8b")


@mcp_server.tool()
@with_hooks("ask_granite")
async def ask_granite(prompt: str) -> str:
    """IBM Granite 3.1 8B — fact-checking; low hallucination rate."""
    return await _call(
        "ask_granite", prompt, primary="ollama", model="granite3.1-dense:8b"
    )


@mcp_server.tool()
@with_hooks("ask_granite_fast")
async def ask_granite_fast(prompt: str) -> str:
    """Granite 2B — micro-verifier (<2s)."""
    return await _call(
        "ask_granite_fast", prompt, primary="ollama", model="granite3.1-dense:2b"
    )


@mcp_server.tool()
@with_hooks("ask_starcoder")
async def ask_starcoder(prompt: str) -> str:
    """StarCoder2 3B — fill-in-the-middle completion and fast lint."""
    return await _call("ask_starcoder", prompt, primary="ollama", model="starcoder2:3b")


@mcp_server.tool()
@with_hooks("ask_deepseek")
async def ask_deepseek(prompt: str) -> str:
    """DeepSeek Coder v2 16B — bug finder; line-by-line review."""
    return await _call(
        "ask_deepseek", prompt, primary="ollama", model="deepseek-coder-v2:16b"
    )


@mcp_server.tool()
@with_hooks("ask_codellama")
async def ask_codellama(prompt: str) -> str:
    """CodeLlama 7B — lightweight code and unit-test generation."""
    return await _call("ask_codellama", prompt, primary="ollama", model="codellama:7b")


@mcp_server.tool()
@with_hooks("ask_gemma2")
async def ask_gemma2(prompt: str) -> str:
    """Gemma 2 9B — factual answers; low hallucination rate."""
    return await _call("ask_gemma2", prompt, primary="ollama", model="gemma2:9b")


@mcp_server.tool()
@with_hooks("ask_llava")
async def ask_llava(prompt: str) -> str:
    """Llava 7B — local image understanding (multimodal)."""
    return await _call("ask_llava", prompt, primary="ollama", model="llava:7b")


@mcp_server.tool()
@with_hooks("ask_longcontext")
async def ask_longcontext(prompt: str) -> str:
    """Kimi K2.5 (CF) — 256K context long-context alias."""
    return await _call(
        "ask_longcontext",
        prompt,
        primary="cloudflare",
        model="@cf/moonshotai/kimi-k2.5",
    )


@mcp_server.tool()
@with_hooks("ask_or_qwen_coder")
async def ask_or_qwen_coder(prompt: str) -> str:
    """OpenRouter Qwen3 Coder 480B :free — SWE-Bench 69.6%."""
    return await _call(
        "ask_or_qwen_coder",
        prompt,
        primary="openrouter",
        model="qwen/qwen3-coder:free",
    )


@mcp_server.tool()
@with_hooks("ask_or_minimax")
async def ask_or_minimax(prompt: str) -> str:
    """OpenRouter MiniMax M2 :free — cache_control destekli."""
    return await _call(
        "ask_or_minimax",
        prompt,
        primary="openrouter",
        model="minimax/minimax-m2:free",
    )


@mcp_server.tool()
@with_hooks("ask_vllm")
async def ask_vllm(prompt: str) -> str:
    """vLLM cluster — self-hosted. Requires ABS_VLLM_URL."""
    return await _call("ask_vllm", prompt, primary="vllm", model="default")


@mcp_server.tool()
@with_hooks("ask_reasoner")
async def ask_reasoner(prompt: str) -> str:
    """CF DeepSeek R1 Distill Qwen 32B — edge reasoning."""
    return await _call(
        "ask_reasoner",
        prompt,
        primary="cloudflare",
        model="@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
    )


# MLX — Apple Silicon Neural Engine


@mcp_server.tool()
@with_hooks("ask_mlx")
async def ask_mlx(prompt: str) -> str:
    """MLX Neural Engine — llama3-8b on Apple Silicon, ~0.3-1s."""
    return await _call("ask_mlx", prompt, primary="mlx", model="llama3-8b")


@mcp_server.tool()
@with_hooks("ask_mlx_fast")
async def ask_mlx_fast(prompt: str) -> str:
    """MLX Fast — phi3-mini; classification in under 0.5s."""
    return await _call("ask_mlx_fast", prompt, primary="mlx", model="phi3-mini")


REGISTERED_TOOLS.extend(
    [
        "ask_smart",
        "ask_rerank",
        "ask_aya",
        "ask_granite",
        "ask_granite_fast",
        "ask_starcoder",
        "ask_deepseek",
        "ask_codellama",
        "ask_gemma2",
        "ask_llava",
        "ask_longcontext",
        "ask_or_qwen_coder",
        "ask_or_minimax",
        "ask_vllm",
        "ask_reasoner",
        "ask_mlx",
        "ask_mlx_fast",
    ]
)
