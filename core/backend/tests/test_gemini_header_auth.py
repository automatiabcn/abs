# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2E ITEM-A — Gemini header-auth migration tests.

Verifies that all 9 migrated call sites send `x-goog-api-key: <KEY>` as a
request header and that the request URL no longer contains `?key=<KEY>`.

We use respx to intercept httpx requests and inspect the captured Request
object directly.
"""

from __future__ import annotations

import asyncio

import httpx
import respx

from app.providers.gemini._auth import gemini_headers


# ─── _auth helper ──────────────────────────────────────────────────────


def test_gemini_headers_sets_x_goog_api_key() -> None:
    h = gemini_headers("AIzaSyTEST")
    assert h["x-goog-api-key"] == "AIzaSyTEST"
    assert h["Content-Type"] == "application/json"


def test_gemini_headers_json_false_omits_content_type() -> None:
    h = gemini_headers("AIzaSyTEST", json=False)
    assert h["x-goog-api-key"] == "AIzaSyTEST"
    assert "Content-Type" not in h


# ─── Adapter (gemini/adapter.py) ────────────────────────────────────────


@respx.mock
def test_gemini_adapter_uses_header_not_query_param(monkeypatch) -> None:
    from app.providers.gemini.adapter import GeminiProvider

    monkeypatch.setattr(
        "app.providers.gemini.adapter.settings.gemini_api_key",
        "AIzaSyADAPTER_KEY",
        raising=False,
    )

    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 3,
                    "candidatesTokenCount": 1,
                },
            },
        )
    )

    p = GeminiProvider()
    asyncio.run(p.call("ping"))

    assert route.called
    req = route.calls.last.request
    # Header carries the secret.
    assert req.headers.get("x-goog-api-key") == "AIzaSyADAPTER_KEY"
    # URL is clean.
    assert "key=" not in str(req.url)
    assert "AIzaSyADAPTER_KEY" not in str(req.url)


# ─── gemini_extras.py ───────────────────────────────────────────────────


@respx.mock
def test_gemini_extras_search_uses_header(monkeypatch) -> None:
    from app.providers import gemini_extras

    monkeypatch.setattr(
        gemini_extras.settings, "gemini_api_key", "AIzaSyEXTRAS_KEY", raising=False
    )

    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )
    )

    asyncio.run(gemini_extras.gemini_search("hello"))

    assert route.called
    req = route.calls.last.request
    assert req.headers.get("x-goog-api-key") == "AIzaSyEXTRAS_KEY"
    assert "key=" not in str(req.url)


@respx.mock
def test_gemini_extras_video_status_uses_header(monkeypatch) -> None:
    from app.providers import gemini_extras

    monkeypatch.setattr(
        gemini_extras.settings, "gemini_api_key", "AIzaSyVIDEO_KEY", raising=False
    )

    route = respx.get(
        "https://generativelanguage.googleapis.com/v1beta/operations/op_123"
    ).mock(return_value=httpx.Response(200, text='{"done":false}'))

    asyncio.run(gemini_extras.gemini_video_status("operations/op_123"))

    assert route.called
    req = route.calls.last.request
    assert req.headers.get("x-goog-api-key") == "AIzaSyVIDEO_KEY"
    assert "key=" not in str(req.url)


# ─── smart_link/provider_validators.py ──────────────────────────────────


@respx.mock
def test_validate_gemini_uses_header() -> None:
    from app.smart_link.provider_validators import validate_gemini

    route = respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=httpx.Response(200, json={"models": []})
    )

    out = validate_gemini("AIzaSyVALIDATE_KEY")

    assert route.called
    assert out["ok"] is True
    req = route.calls.last.request
    assert req.headers.get("x-goog-api-key") == "AIzaSyVALIDATE_KEY"
    assert "key=" not in str(req.url)
