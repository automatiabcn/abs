# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pact-style canonical request/response validator for ABS providers."""

from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
from typing import Any

PROVIDERS: tuple[str, ...] = ("anthropic", "groq", "gemini", "cohere", "openrouter")


def _provider_dir(provider: str) -> pathlib.Path:
    mod = importlib.import_module(f"app.providers.{provider}")
    f = mod.__file__
    if f is None:
        raise RuntimeError(f"provider {provider} has no __file__")
    return pathlib.Path(f).parent


def load_fixture(provider: str, kind: str, version: str = "v1") -> dict[str, Any]:
    """Load a contracts/{kind}_{version}.json fixture for *provider*."""
    path = _provider_dir(provider) / "contracts" / f"{kind}_{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(payload: dict[str, Any]) -> str:
    """Stable sha256 of a JSON payload — used by nightly drift checks."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def assert_canonical_request(provider: str, payload: dict[str, Any]) -> None:
    if provider == "anthropic":
        for k in ("model", "max_tokens", "messages"):
            assert k in payload, f"anthropic request missing {k!r}"
        msgs = payload["messages"]
        assert isinstance(msgs, list) and msgs, (
            "anthropic messages must be non-empty list"
        )
        for m in msgs:
            assert "role" in m and "content" in m, (
                "anthropic message missing role/content"
            )
        return
    if provider in ("groq", "openrouter", "cohere"):
        for k in ("model", "messages"):
            assert k in payload, f"{provider} request missing {k!r}"
        msgs = payload["messages"]
        assert isinstance(msgs, list) and msgs, (
            f"{provider} messages must be non-empty list"
        )
        for m in msgs:
            assert "role" in m and "content" in m, (
                f"{provider} message missing role/content"
            )
        return
    if provider == "gemini":
        contents = payload.get("contents")
        assert isinstance(contents, list) and contents, (
            "gemini contents must be non-empty list"
        )
        for c in contents:
            parts = c.get("parts")
            assert isinstance(parts, list) and parts, (
                "gemini parts must be non-empty list"
            )
            assert "text" in parts[0], "gemini first part needs text"
        return
    raise AssertionError(f"unknown provider {provider!r}")


def assert_canonical_response(provider: str, payload: dict[str, Any]) -> None:
    if provider == "anthropic":
        content = payload.get("content")
        assert isinstance(content, list) and content, (
            "anthropic response.content must be non-empty list"
        )
        first = content[0]
        assert (
            first.get("type") == "text"
            and isinstance(first.get("text"), str)
            and first["text"]
        ), "anthropic first content block must be text with non-empty text"
        return
    if provider in ("groq", "openrouter"):
        choices = payload.get("choices")
        assert isinstance(choices, list) and choices, (
            f"{provider} response.choices required"
        )
        msg = choices[0].get("message")
        assert isinstance(msg, dict), f"{provider} response.choices[0].message required"
        assert isinstance(msg.get("content"), str) and msg["content"], (
            f"{provider} response.choices[0].message.content must be non-empty string"
        )
        return
    if provider == "gemini":
        cands = payload.get("candidates")
        assert isinstance(cands, list) and cands, "gemini response.candidates required"
        parts = cands[0].get("content", {}).get("parts", [])
        assert parts and isinstance(parts[0].get("text"), str) and parts[0]["text"], (
            "gemini first candidate part text required"
        )
        return
    if provider == "cohere":
        msg = payload.get("message")
        assert isinstance(msg, dict), "cohere response.message required"
        content = msg.get("content")
        assert isinstance(content, list) and content, (
            "cohere response.message.content required"
        )
        assert isinstance(content[0].get("text"), str) and content[0]["text"], (
            "cohere first content block text required"
        )
        return
    raise AssertionError(f"unknown provider {provider!r}")


def canonical_text(provider: str, response: dict[str, Any]) -> str:
    """Extract the assistant message text into the canonical ABS shape."""
    if provider == "anthropic":
        return "".join(
            b.get("text", "")
            for b in response.get("content", [])
            if b.get("type") == "text"
        )
    if provider in ("groq", "openrouter"):
        return response["choices"][0]["message"]["content"]
    if provider == "gemini":
        return "".join(
            p.get("text", "") for p in response["candidates"][0]["content"]["parts"]
        )
    if provider == "cohere":
        return "".join(b.get("text", "") for b in response["message"]["content"])
    raise AssertionError(f"unknown provider {provider!r}")


__all__ = [
    "PROVIDERS",
    "assert_canonical_request",
    "assert_canonical_response",
    "canonical_text",
    "fingerprint",
    "load_fixture",
]
