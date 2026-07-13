# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Gemini extras — image generation, video generation, Google Search grounding,
URL context, structured output.

These modalities have no OpenAI-compatible equivalent, so they call Gemini's
native endpoints directly rather than going through the shared chat helper.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.providers.gemini._auth import gemini_headers
from app.providers.schemas import ProviderError, ProviderResponse


_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _require_key() -> str:
    if not settings.gemini_api_key:
        raise ProviderError(
            "Gemini API key is not configured", provider="gemini", transient=False
        )
    return settings.gemini_api_key


async def _post(url: str, body: dict, *, key: str, timeout: float = 90.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=gemini_headers(key), json=body)
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
    try:
        return r.json()
    except ValueError as exc:
        # 2xx with a malformed body — raise the same ProviderError(transient)
        # the main gemini adapter uses, so a caller wrapping this for
        # resilience can fail over instead of seeing a bare ValueError.
        raise ProviderError(
            "Gemini JSON parse error", provider="gemini", transient=True
        ) from exc


def _collect_text(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if "text" in p)
    except (KeyError, IndexError, TypeError):
        return ""


async def gemini_search(
    prompt: str, *, model: str = "gemini-2.5-flash"
) -> ProviderResponse:
    """Answer grounded in Google Search, with its sources appended to the text."""
    key = _require_key()
    body: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent", body, key=key)
    elapsed = int((time.monotonic() - start) * 1000)
    text = _collect_text(data)

    # Append the grounding sources when Gemini returns them — an answer that
    # claims to be grounded is only useful if the caller can check it.
    try:
        grounding = data["candidates"][0].get("groundingMetadata") or {}
        citations = grounding.get("groundingChunks") or []
        if citations:
            text += "\n\nSources:\n"
            for i, c in enumerate(citations[:5], 1):
                uri = (c.get("web") or {}).get("uri", "")
                title = (c.get("web") or {}).get("title", "")
                if uri:
                    text += f"  {i}. {title or uri} — {uri}\n"
    except Exception:
        pass

    return ProviderResponse(text=text, model=model, provider="gemini", elapsed_ms=elapsed)


async def gemini_url(url: str, question: str = "Summarize this page", *, model: str = "gemini-2.5-flash") -> ProviderResponse:
    """URL context — ask a question about the content of a URL; Gemini fetches it."""
    key = _require_key()
    body = {
        "contents": [{"parts": [{"text": f"{question}\n\n{url}"}]}],
        "tools": [{"url_context": {}}],
    }
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent", body, key=key)
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
    data = await _post(f"{_BASE}/models/{model}:generateContent", body, key=key)
    elapsed = int((time.monotonic() - start) * 1000)
    return ProviderResponse(
        text=_collect_text(data), model=model, provider="gemini", elapsed_ms=elapsed
    )


async def gemini_image(
    prompt: str,
    *,
    model: str = "gemini-2.5-flash-image",
) -> ProviderResponse:
    """Gemini image generation — returns a base64 PNG."""
    key = _require_key()
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    start = time.monotonic()
    data = await _post(f"{_BASE}/models/{model}:generateContent", body, key=key, timeout=120.0)
    elapsed = int((time.monotonic() - start) * 1000)
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
    """Edit the given image according to the prompt."""
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
        f"{_BASE}/models/gemini-2.5-flash-image:generateContent",
        body,
        key=key,
        timeout=120.0,
    )
    return ProviderResponse(
        text=_collect_text(data) or "[IMAGE edited]",
        model="gemini-2.5-flash-image",
        provider="gemini",
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


_DESCRIBE_PROMPT = (
    "Describe this image in detail for semantic search and retrieval. Cover the "
    "main subject, any visible text (verbatim), objects, people, layout, colours, "
    "charts/numbers, and the apparent purpose. Write a single dense paragraph, no "
    "preamble."
)


async def describe_image(
    image_base64: str,
    mime_type: str = "image/png",
    *,
    prompt: str | None = None,
    model: str = "gemini-2.5-flash",
) -> ProviderResponse:
    """Vision-describe an image so it can be embedded into the (text) RAG index.

    Gemini has no native image-embedding endpoint (only Vertex AI does), so the
    pragmatic path is: Gemini vision produces a rich textual description, which
    the existing text embedder turns into a vector. Returns the description in
    ``ProviderResponse.text``.
    """
    key = _require_key()
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt or _DESCRIBE_PROMPT},
                    {"inlineData": {"mimeType": mime_type, "data": image_base64}},
                ]
            }
        ]
    }
    start = time.monotonic()
    data = await _post(
        f"{_BASE}/models/{model}:generateContent", body, key=key, timeout=90.0
    )
    return ProviderResponse(
        text=_collect_text(data),
        model=model,
        provider="gemini",
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


async def gemini_video(prompt: str) -> ProviderResponse:
    """Start a video generation job. Returns the operation name — generation is
    long-running, so the caller polls gemini_video_status with it."""
    key = _require_key()
    body = {"instances": [{"prompt": prompt}]}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_BASE}/models/veo-3.0-generate-001:predictLongRunning",
                headers=gemini_headers(key),
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
    """Poll a video job by operation name."""
    key = _require_key()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_BASE}/{operation_name}",
                headers=gemini_headers(key, json=False),
            )
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Gemini video status: {exc}", provider="gemini", transient=True
        ) from exc
    return ProviderResponse(text=r.text, model="veo-3.0", provider="gemini", elapsed_ms=0)
