# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Gemini modality tools — image (x3), video (x3), lite, url, search, structured."""

from __future__ import annotations

import json
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers import gemini_extras as _gx
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


async def _safe(tool_name: str, coro):
    await tracker.bump(tool_name)
    try:
        resp = await coro
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] {tool_name}: {exc.message}"


@mcp_server.tool()
@with_hooks("gemini_image")
async def gemini_image(prompt: str) -> str:
    """Gemini 2.5 Flash Image — generate an image from a prompt (base64 PNG)."""
    return await _safe("gemini_image", _gx.gemini_image(prompt))


@mcp_server.tool()
@with_hooks("gemini_image_pro")
async def gemini_image_pro(prompt: str) -> str:
    """Gemini Image Pro (Nano Banana Pro) — higher-quality image generation."""
    return await _safe("gemini_image_pro", _gx.gemini_image_pro(prompt))


@mcp_server.tool()
@with_hooks("gemini_image_edit")
async def gemini_image_edit(prompt: str, image_base64: str) -> str:
    """Edit a base64 image according to the prompt."""
    return await _safe("gemini_image_edit", _gx.gemini_image_edit(prompt, image_base64))


@mcp_server.tool()
@with_hooks("gemini_video")
async def gemini_video(prompt: str) -> str:
    """Start a Veo 3.0 video job. Returns an operation name — video generation is
    long-running, so poll it with gemini_video_status."""
    return await _safe("gemini_video", _gx.gemini_video(prompt))


@mcp_server.tool()
@with_hooks("gemini_video_status")
async def gemini_video_status(operation_name: str) -> str:
    """Poll a video job by the operation name gemini_video returned."""
    return await _safe("gemini_video_status", _gx.gemini_video_status(operation_name))


@mcp_server.tool()
@with_hooks("gemini_video_wait")
async def gemini_video_wait(operation_name: str, max_seconds: int = 300) -> str:
    """Block until a video job finishes, polling every 15s, up to max_seconds."""
    await tracker.bump("gemini_video_wait")
    import asyncio

    elapsed = 0
    interval = 15
    while elapsed < max_seconds:
        try:
            resp = await _gx.gemini_video_status(operation_name)
            if '"done": true' in (resp.text or "").lower():
                return resp.text
        except ProviderError as exc:
            return f"[ERROR] gemini_video_wait: {exc.message}"
        await asyncio.sleep(interval)
        elapsed += interval
    return f"[TIMEOUT] video not finished after {max_seconds}s: {operation_name}"


@mcp_server.tool()
@with_hooks("gemini_lite")
async def gemini_lite(prompt: str) -> str:
    """Gemini Flash Lite — cheapest, fastest single-shot answer."""
    from app.providers.registry import get_provider

    await tracker.bump("gemini_lite")
    try:
        provider = get_provider("gemini")
        resp = await provider.call(
            prompt, model="gemini-2.5-flash-lite", max_tokens=1024
        )
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] gemini_lite: {exc.message}"


@mcp_server.tool()
@with_hooks("gemini_url")
async def gemini_url(url: str, question: str = "Summarize this page") -> str:
    """Ask a question about the contents of a URL (Gemini fetches it itself)."""
    return await _safe("gemini_url", _gx.gemini_url(url, question))


@mcp_server.tool()
@with_hooks("gemini_search")
async def gemini_search(prompt: str) -> str:
    """Answer grounded in Google Search, with the source URLs appended."""
    return await _safe("gemini_search", _gx.gemini_search(prompt))


@mcp_server.tool()
@with_hooks("gemini_structured")
async def gemini_structured(prompt: str, schema_json: str) -> str:
    """Schema-guaranteed JSON output. schema_json must be a valid JSON schema."""
    await tracker.bump("gemini_structured")
    try:
        schema = json.loads(schema_json)
    except Exception as exc:
        return f"[ERROR] gemini_structured: invalid schema_json ({exc})"
    try:
        resp = await _gx.gemini_structured(prompt, schema)
        return resp.text or ""
    except ProviderError as exc:
        return f"[ERROR] gemini_structured: {exc.message}"


REGISTERED_TOOLS.extend(
    [
        "gemini_image",
        "gemini_image_pro",
        "gemini_image_edit",
        "gemini_video",
        "gemini_video_status",
        "gemini_video_wait",
        "gemini_lite",
        "gemini_url",
        "gemini_search",
        "gemini_structured",
    ]
)
