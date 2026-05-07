# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.1 — TTS HTTP surface.

Endpoints:
  GET  /v1/tts/voices            → catalog
  POST /v1/tts/synthesize        → audio/wav

Auth: panel session cookie (`current_admin`). Request guarded so a runaway
loop can't push a 1MB blob through Piper — text capped at 2000 chars per call.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.services import feature_usage as feature_usage_service
from app.services.tts import (
    DEFAULT_VOICE_ID,
    DEFAULT_VOICES,
    PiperUnavailableError,
    list_voices,
    synthesize,
)

router = APIRouter(prefix="/v1/tts", tags=["tts"])
logger = logging.getLogger(__name__)


MAX_TEXT_LENGTH = 2000


class SynthRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    voice: str = DEFAULT_VOICE_ID


@router.get("/voices")
async def voices(_admin: dict = Depends(current_admin)) -> dict:
    return {"default": DEFAULT_VOICE_ID, "voices": list_voices()}


@router.post("/synthesize")
async def synthesize_endpoint(
    body: SynthRequest, admin: dict = Depends(current_admin)
) -> Response:
    if body.voice not in DEFAULT_VOICES:
        raise HTTPException(400, "unknown voice")
    try:
        wav = await synthesize(body.text, body.voice)
    except PiperUnavailableError as exc:
        logger.warning("piper unavailable: %s", exc)
        raise HTTPException(503, f"piper_unavailable: {exc}") from exc
    try:
        feature_usage_service.increment(
            "tts_synthesize", actor_email=admin.get("sub")
        )
    except Exception:
        pass
    return Response(content=wav, media_type="audio/wav")
