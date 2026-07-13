# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""System, cache and patch tools — cache_stats, quota_status, model_health,
code_fingerprint, and the two patch tools (off by default, see the note below)."""

from __future__ import annotations

import hashlib
import json
from typing import List

from app.cascade.breaker import default_breaker
from app.cascade.cache import default_cache
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.patches import apply_patch as _apply_patch
from app.patches import preview_patch as _preview_patch

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("cache_stats")
async def cache_stats() -> str:
    """Semantic cache statistics (hit/miss/entries/hit_rate)."""
    await tracker.bump("cache_stats")
    return json.dumps(default_cache.stats(), ensure_ascii=False)


@mcp_server.tool()
@with_hooks("quota_status")
async def quota_status() -> str:
    """Provider quota state, as seen through the circuit breakers."""
    await tracker.bump("quota_status")
    configured = {
        "groq": bool(settings.groq_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "gemini": bool(settings.gemini_api_key),
        "cloudflare": bool(settings.cf_account_id and settings.cf_api_token),
        "anthropic": bool(settings.anthropic_api_key),
        "cohere": bool(settings.cohere_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "vllm": bool(settings.vllm_url),
        "ollama": bool(settings.ollama_url),
    }
    return json.dumps(
        {
            "configured": configured,
            "breakers": default_breaker.snapshot(),
            "note": "Breaker state only. Per-provider RPM/TPM/TPD is not fetched from the provider APIs.",
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("model_health")
async def model_health() -> str:
    """Health score per provider, derived from breaker state and failure count."""
    await tracker.bump("model_health")
    breakers = default_breaker.snapshot()
    results = {}
    for name, st in breakers.items():
        state = st.get("state", "closed")
        fails = int(st.get("fail_count") or 0)
        score = 10.0 if state == "closed" else (5.0 if state == "half_open" else 2.0)
        score -= min(fails * 0.5, 3.0)
        results[name] = {
            "state": state,
            "fail_count": fails,
            "health_score": max(0.0, score),
        }
    # No calls yet is not ill health — report healthy rather than zero.
    if not results:
        return json.dumps({"note": "no provider calls yet", "default_health": 10.0})
    return json.dumps(results, ensure_ascii=False)


@mcp_server.tool()
@with_hooks("code_fingerprint")
async def code_fingerprint(code: str) -> str:
    """Fingerprint a snippet: SHA-256, line count, and AST metrics."""
    await tracker.bump("code_fingerprint")
    from app.judge.ast_metrics import ast_metrics

    metrics = ast_metrics(code) if code else {}
    return json.dumps(
        {
            "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "lines": code.count("\n") + 1 if code else 0,
            "chars": len(code),
            "ast_metrics": metrics,
        },
        ensure_ascii=False,
        indent=2,
    )


@with_hooks("preview_patch")
async def preview_patch(file_path: str, unified_diff: str) -> str:
    """Dry-run a unified diff. Returns success plus the reason it would fail."""
    await tracker.bump("preview_patch")
    return json.dumps(_preview_patch(file_path, unified_diff), ensure_ascii=False)


@with_hooks("apply_patch")
async def apply_patch(file_path: str, unified_diff: str, backup: bool = True) -> str:
    """Apply a unified diff atomically, with a backup. On failure the file is
    rolled back and the reason returned."""
    await tracker.bump("apply_patch")
    return json.dumps(
        _apply_patch(file_path, unified_diff, backup=backup), ensure_ascii=False
    )


REGISTERED_TOOLS.extend(
    [
        "cache_stats",
        "quota_status",
        "model_health",
        "code_fingerprint",
    ]
)

# SECURITY: preview_patch / apply_patch read + WRITE arbitrary existing files
# on the server (the patch engine takes Path(file_path) with no allowlist or
# traversal guard). Exposed over the network /mcp transport they give ANY
# token-holder — including turnkey team members who only hold a delegation
# token — arbitrary file read (secret disclosure) and write (RCE: patch a
# loaded module or admin_credentials.json). They are operator-local dev tools,
# so keep them OFF the MCP surface by default. An operator driving their OWN
# deployment via Claude Code can opt in with ABS_MCP_EXPOSE_PATCH_TOOLS=1.
if getattr(settings, "mcp_expose_patch_tools", False):
    preview_patch = mcp_server.tool()(preview_patch)
    apply_patch = mcp_server.tool()(apply_patch)
    REGISTERED_TOOLS.extend(["preview_patch", "apply_patch"])
