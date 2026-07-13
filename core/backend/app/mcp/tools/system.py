# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The system_status MCP tool — license, providers, cache, tool usage."""

from __future__ import annotations

from app.cascade.breaker import default_breaker
from app.cascade.cache import default_cache
from app.config import settings
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker


@mcp_server.tool()
async def system_status() -> dict:
    """System status: license, provider circuit-breaker state, cache, tool usage.

    `configured` reports whether a key is present, never the key itself.
    """
    await tracker.bump("system_status")

    configured = {
        "groq": bool(settings.groq_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "gemini": bool(settings.gemini_api_key),
        "cloudflare": bool(settings.cf_account_id and settings.cf_api_token),
        "anthropic": bool(settings.anthropic_api_key),
        "cohere": bool(settings.cohere_api_key),
        "ollama": bool(settings.ollama_url),
    }

    return {
        "product": "Automatia ABS",
        "version": "0.1.0",
        "license": {
            "configured": bool(settings.license_key),
            "require_for_mcp": settings.mcp_require_license,
        },
        "providers": {
            "configured": configured,
            "breakers": default_breaker.snapshot(),
        },
        "cache": default_cache.stats(),
        "tools": tracker.snapshot(),
    }
