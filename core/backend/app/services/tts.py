# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.1 — Piper TTS service client.

Piper (MIT, https://github.com/rhasspy/piper) replaces Coqui XTTS-v2 as the
Self-hosted TTS engine. Attribution is in `THIRD_PARTY_LICENSES.md`.

Container: `piper` (compose service) on :5002 — see infra/piper/Dockerfile.

API contract (our thin wrapper):
  POST /api/tts  body={"text": "...", "voice": "tr_TR-fettah-medium"}
  → 200 audio/wav (PCM 16-bit 22050 Hz, mono)
  → 400 unknown voice
"""

from __future__ import annotations

import logging
import os
from typing import Final

import httpx

logger = logging.getLogger(__name__)


PIPER_BASE_URL: Final[str] = os.environ.get(
    "ABS_PIPER_URL", "http://piper:5002"
)
PIPER_TIMEOUT_SECONDS: Final[float] = float(
    os.environ.get("ABS_PIPER_TIMEOUT_SECONDS", "30")
)


# Public catalog — voices we ship by default. Operator can install more
# via piper container's /api/voices upload, but the API only accepts known IDs.
DEFAULT_VOICES: Final[dict[str, str]] = {
    "tr_TR-fettah-medium": "Turkish male, medium quality (Piper default tr)",
    "en_US-amy-medium": "English (US) female, medium quality",
    "es_ES-davefx-medium": "Spanish (ES) male, medium quality",
}
DEFAULT_VOICE_ID: Final[str] = "tr_TR-fettah-medium"


class PiperUnavailableError(RuntimeError):
    """Raised when piper container is unreachable / returns non-2xx.
    Wrapped at API layer to a 503 so the customer sees a clean message
    rather than a Python traceback.
    """


async def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE_ID,
) -> bytes:
    """Return WAV bytes for `text`. Falls through `httpx` errors as
    PiperUnavailableError so the API layer can shape the response."""
    if voice not in DEFAULT_VOICES:
        raise ValueError(f"unknown voice: {voice}")
    payload = {"text": text, "voice": voice}
    try:
        async with httpx.AsyncClient(
            base_url=PIPER_BASE_URL, timeout=PIPER_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post("/api/tts", json=payload)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("piper synth failed (%s): %s", voice, exc)
        raise PiperUnavailableError(str(exc)) from exc
    body = resp.content
    if len(body) < 44 or body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise PiperUnavailableError(
            f"piper returned non-WAV body ({len(body)} bytes)"
        )
    return body


def list_voices() -> dict[str, str]:
    """Catalog used by /v1/tts/voices endpoint + frontend dropdown."""
    return dict(DEFAULT_VOICES)
