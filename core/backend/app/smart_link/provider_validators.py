# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""026 — Provider API key validators.

Each validator does a minimal probe to confirm the key is valid.
Live API calls; tests use `monkeypatch httpx`.

Output: {ok: bool, latency_ms: int, error: str | null}
Timeout: 5 seconds per provider.
"""

from __future__ import annotations

import time
from typing import Callable, Dict

import httpx


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _result(ok: bool, t0: float, error: str | None = None) -> dict:
    return {
        "ok": ok,
        "latency_ms": round(_now_ms() - t0, 1),
        "error": error,
    }


def validate_openai(api_key: str) -> dict:
    t0 = _now_ms()
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            return _result(True, t0)
        return _result(False, t0, f"HTTP {r.status_code}")
    except Exception as exc:
        return _result(False, t0, str(exc)[:200])


def validate_anthropic(api_key: str) -> dict:
    t0 = _now_ms()
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        if r.status_code in (200, 400):  # 400 is "auth ok, payload bad" → key valid
            return _result(True, t0)
        if r.status_code in (401, 403):
            return _result(False, t0, "Invalid API key")
        return _result(False, t0, f"HTTP {r.status_code}")
    except Exception as exc:
        return _result(False, t0, str(exc)[:200])


def validate_cohere(api_key: str) -> dict:
    t0 = _now_ms()
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(
                "https://api.cohere.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            return _result(True, t0)
        return _result(False, t0, f"HTTP {r.status_code}")
    except Exception as exc:
        return _result(False, t0, str(exc)[:200])


def validate_groq(api_key: str) -> dict:
    t0 = _now_ms()
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            return _result(True, t0)
        return _result(False, t0, f"HTTP {r.status_code}")
    except Exception as exc:
        return _result(False, t0, str(exc)[:200])


def validate_gemini(api_key: str) -> dict:
    t0 = _now_ms()
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": api_key},
            )
        if r.status_code == 200:
            return _result(True, t0)
        return _result(False, t0, f"HTTP {r.status_code}")
    except Exception as exc:
        return _result(False, t0, str(exc)[:200])


VALIDATORS: Dict[str, Callable[[str], dict]] = {
    "openai": validate_openai,
    "anthropic": validate_anthropic,
    "cohere": validate_cohere,
    "groq": validate_groq,
    "gemini": validate_gemini,
}


def validate(provider: str, api_key: str) -> dict:
    fn = VALIDATORS.get(provider)
    if fn is None:
        return {"ok": False, "latency_ms": 0, "error": f"Unknown provider: {provider}"}
    return fn(api_key)
