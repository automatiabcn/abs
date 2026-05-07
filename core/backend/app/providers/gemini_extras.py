# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Gemini extras — image generation, video generation, Google Search, URL context, structured output.

REST API çağrıları `app.providers.base.openai_compatible_chat` değil, Gemini'nin
native endpoint'lerine gider. Base GeminiProvider generateContent paylaşır; buradaki
fonksiyonlar Gemini-spesifik modality'leri sağlar.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.providers.schemas import ProviderError, ProviderResponse


_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _require_key() -> str:
    if not settings.gemini_api_key:
        raise ProviderError(
            "Gemini API key tanımlı değil", provider="gemini", transient=False
        )
    return settings.gemini_api_key


async def _post(url: str, body: dict, *, timeout: float = 90.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers={"Content-Type": "application/json"}, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Gemini HTTP: {exc}", provider="gemini", transient=True
        ) from exc

    if r.status_code == 429:
        raise ProviderError("Gemini rate limit", provider="gemini", transient=True)
    if r.status_code >= 500:
        raise ProviderError(f"Gemini 5xx: {r.status_code}", provider="gemini", transient=True)
    if r.status_code >= 400:
        raise ProviderError(
            f"Gemini {r.status_code}: {r.text[:200]}",
            provider="gemini",
            transient=False,
        )
    return r.json()


def _collect_text(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if "text" in p)
    except (KeyError, IndexError, TypeError):
        return ""


async def gemini_search(
    prompt: str, *, model: str = "gemini-2.5-flash"
) -> ProviderResponse:
    """Google Search grounded yanıt + kaynaklar."""
    key = _require_key()
    body: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent?key={key}", body)
    elapsed = int((time.monotonic() - start) * 1000)
    text = _collect_text(data)

    # Grounding metadata (kaynaklar) varsa bağla
    try:
        grounding = data["candidates"][0].get("groundingMetadata") or {}
        citations = grounding.get("groundingChunks") or []
        if citations:
            text += "\n\nKaynaklar:\n"
            for i, c in enumerate(citations[:5], 1):
                uri = (c.get("web") or {}).get("uri", "")
                title = (c.get("web") or {}).get("title", "")
                if uri:
                    text += f"  {i}. {title or uri} — {uri}\n"
    except Exception:
        pass

    return ProviderResponse(text=text, model=model, provider="gemini", elapsed_ms=elapsed)


async def gemini_url(url: str, question: str = "Bu sayfayı özetle", *, model: str = "gemini-2.5-flash") -> ProviderResponse:
    """URL context — bir URL'yi verip içerik hakkında soru sor."""
    key = _require_key()
    body = {
        "contents": [{"parts": [{"text": f"{question}\n\n{url}"}]}],
        "tools": [{"url_context": {}}],
    }
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent?key={key}", body)
    elapsed = int((time.monotonic() - start) * 1000)
    return ProviderResponse(
        text=_collect_text(data), model=model, provider="gemini", elapsed_ms=elapsed
    )


async def gemini_structured(prompt: str, schema: dict, *, model: str = "gemini-2.5-flash") -> ProviderResponse:
    """JSON schema-guaranteed output."""
    key = _require_key()
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent?key={key}", body)
    elapsed = int((time.monotonic() - start) * 1000)
    return ProviderResponse(
        text=_collect_text(data), model=model, provider="gemini", elapsed_ms=elapsed
    )


async def gemini_image(
    prompt: str,
    *,
    model: str = "gemini-2.5-flash-image",
) -> ProviderResponse:
    """Gemini Image generation — base64 PNG döner."""
    key = _require_key()
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent?key={key}", body, timeout=120.0)
    elapsed = int((time.monotonic() - start) * 1000)
    # İlk image part'ını al
    text_parts: List[str] = []
    try:
        for p in data["candidates"][0]["content"]["parts"]:
            inline = p.get("inlineData") or {}
            if inline.get("data"):
                text_parts.append(
                    f"[IMAGE base64 {inline.get('mimeType','image/png')} "
                    f"{len(inline['data'])} bytes]"
                )
            elif "text" in p:
                text_parts.append(p["text"])
    except (KeyError, IndexError, TypeError):
        pass
    return ProviderResponse(
        text="\n".join(text_parts) or _collect_text(data),
        model=model,
        provider="gemini",
        elapsed_ms=elapsed,
    )


async def gemini_image_pro(prompt: str) -> ProviderResponse:
    """Gemini image pro — Nano Banana Pro."""
    return await gemini_image(prompt, model="gemini-2.5-flash-image-pro")


async def gemini_image_edit(prompt: str, image_base64: str) -> ProviderResponse:
    """Verilen görseli prompt'a göre düzenle."""
    key = _require_key()
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_base64,
                        }
                    },
                ]
            }
        ]
    }
    start = time.monotonic()
    data = await _post(
        f"{_BASE}/models/gemini-2.5-flash-image:generateContent?key={key}",
        body,
        timeout=120.0,
    )
    return ProviderResponse(
        text=_collect_text(data) or "[IMAGE edited]",
        model="gemini-2.5-flash-image",
        provider="gemini",
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


async def gemini_video(prompt: str) -> ProviderResponse:
    """Video generation job başlat. `operation` name döner (sonra gemini_video_status ile sorgu)."""
    key = _require_key()
    body = {"instances": [{"prompt": prompt}]}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_BASE}/models/veo-3.0-generate-001:predictLongRunning?key={key}",
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Gemini video HTTP: {exc}", provider="gemini", transient=True
        ) from exc
    elapsed = int((time.monotonic() - start) * 1000)
    if r.status_code >= 400:
        raise ProviderError(
            f"Gemini video {r.status_code}: {r.text[:200]}",
            provider="gemini",
            transient=(r.status_code >= 500),
        )
    return ProviderResponse(
        text=r.text, model="veo-3.0-generate-001", provider="gemini", elapsed_ms=elapsed
    )


async def gemini_video_status(operation_name: str) -> ProviderResponse:
    """Video job status — operation adını sorgular."""
    key = _require_key()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{_BASE}/{operation_name}?key={key}")
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Gemini video status: {exc}", provider="gemini", transient=True
        ) from exc
    return ProviderResponse(text=r.text, model="veo-3.0", provider="gemini", elapsed_ms=0)
