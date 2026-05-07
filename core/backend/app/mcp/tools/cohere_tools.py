# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Batch D — 3 Cohere tool (command_r, aya_expanse, embed)."""

from __future__ import annotations

import json
from typing import List

from app.cascade.orchestrator import call_with_cascade
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers.registry import get_provider
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("ask_cohere_command_r")
async def ask_cohere_command_r(prompt: str) -> str:
    """Cohere Command R+ 08-2024 — enterprise chat, RAG uyumlu."""
    await tracker.bump("ask_cohere_command_r")
    try:
        resp = await call_with_cascade(
            prompt, primary="cohere", model="command-r-plus-08-2024"
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] ask_cohere_command_r: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_cohere_aya")
async def ask_cohere_aya(prompt: str) -> str:
    """Cohere Aya Expanse 32B — 101 dil, çok-dilli görev + Türkçe."""
    await tracker.bump("ask_cohere_aya")
    try:
        resp = await call_with_cascade(
            prompt, primary="cohere", model="c4ai-aya-expanse-32b"
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] ask_cohere_aya: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_cohere_embed")
async def ask_cohere_embed(text: str) -> str:
    """Cohere embed-english-v3.0 — 1024-dim embedding döndürür (JSON)."""
    await tracker.bump("ask_cohere_embed")
    try:
        provider = get_provider("cohere")
        if not hasattr(provider, "embed"):
            return "[HATA] ask_cohere_embed: embed method yok"
        vec = await provider.embed(text)  # type: ignore[attr-defined]
        return json.dumps(
            {"dim": len(vec), "preview": vec[:8], "model": "embed-english-v3.0"},
            ensure_ascii=False,
        )
    except ProviderError as exc:
        return f"[HATA] ask_cohere_embed: {exc.message}"


REGISTERED_TOOLS.extend(["ask_cohere_command_r", "ask_cohere_aya", "ask_cohere_embed"])
