"""Batch C — 10 Gemini extras tool (image x3, video x3, lite, url, search, structured)."""

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
        return f"[HATA] {tool_name}: {exc.message}"


@mcp_server.tool()
@with_hooks("gemini_image")
async def gemini_image(prompt: str) -> str:
    """Gemini 2.5 Flash Image — prompt'tan görsel üret (base64 PNG)."""
    return await _safe("gemini_image", _gx.gemini_image(prompt))


@mcp_server.tool()
@with_hooks("gemini_image_pro")
async def gemini_image_pro(prompt: str) -> str:
    """Gemini Image Pro (Nano Banana Pro) — yüksek kalite görsel."""
    return await _safe("gemini_image_pro", _gx.gemini_image_pro(prompt))


@mcp_server.tool()
@with_hooks("gemini_image_edit")
async def gemini_image_edit(prompt: str, image_base64: str) -> str:
    """Verilen base64 görseli prompt'a göre düzenle."""
    return await _safe(
        "gemini_image_edit", _gx.gemini_image_edit(prompt, image_base64)
    )


@mcp_server.tool()
@with_hooks("gemini_video")
async def gemini_video(prompt: str) -> str:
    """Veo 3.0 ile video jobu başlat; operation name döner (sonra status)."""
    return await _safe("gemini_video", _gx.gemini_video(prompt))


@mcp_server.tool()
@with_hooks("gemini_video_status")
async def gemini_video_status(operation_name: str) -> str:
    """Video job durumu sorgula (gemini_video'dan dönen operation name ile)."""
    return await _safe(
        "gemini_video_status", _gx.gemini_video_status(operation_name)
    )


@mcp_server.tool()
@with_hooks("gemini_video_wait")
async def gemini_video_wait(operation_name: str, max_seconds: int = 300) -> str:
    """Video job bitene kadar bekle (polling her 15s). Basit placeholder."""
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
            return f"[HATA] gemini_video_wait: {exc.message}"
        await asyncio.sleep(interval)
        elapsed += interval
    return f"[TIMEOUT] {max_seconds}s sonunda video tamamlanmadı: {operation_name}"


@mcp_server.tool()
@with_hooks("gemini_lite")
async def gemini_lite(prompt: str) -> str:
    """Gemini Flash Lite — hızlı ve düşük maliyetli tek-shot yanıt."""
    from app.providers.registry import get_provider

    await tracker.bump("gemini_lite")
    try:
        provider = get_provider("gemini")
        resp = await provider.call(prompt, model="gemini-2.5-flash-lite", max_tokens=1024)
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] gemini_lite: {exc.message}"


@mcp_server.tool()
@with_hooks("gemini_url")
async def gemini_url(url: str, question: str = "Bu sayfayı özetle") -> str:
    """URL context — bir URL'nin içeriği hakkında soru sor."""
    return await _safe("gemini_url", _gx.gemini_url(url, question))


@mcp_server.tool()
@with_hooks("gemini_search")
async def gemini_search(prompt: str) -> str:
    """Google Search grounded yanıt + kaynak URL'leri."""
    return await _safe("gemini_search", _gx.gemini_search(prompt))


@mcp_server.tool()
@with_hooks("gemini_structured")
async def gemini_structured(prompt: str, schema_json: str) -> str:
    """JSON schema-guaranteed output. schema_json geçerli JSON schema string'i."""
    await tracker.bump("gemini_structured")
    try:
        schema = json.loads(schema_json)
    except Exception as exc:
        return f"[HATA] gemini_structured: invalid schema_json ({exc})"
    try:
        resp = await _gx.gemini_structured(prompt, schema)
        return resp.text or ""
    except ProviderError as exc:
        return f"[HATA] gemini_structured: {exc.message}"


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
