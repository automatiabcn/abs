# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.2 — transcribe HTTP surface.

POST /v1/transcribe         multipart upload, full transcription + diarize
POST /v1/transcribe/stream  5s chunk variant for /panel/transcription live capture

Both routes go through `services.transcribe` which talks to the WhisperX
container. Auth: panel session.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.auth import current_admin
from app.services import feature_usage as feature_usage_service
from app.services.transcribe import (
    WhisperXUnavailableError,
    transcribe_bytes,
    transcribe_path,
)

router = APIRouter(prefix="/v1/transcribe", tags=["transcribe"])
logger = logging.getLogger(__name__)


# Cap per upload — protects ephemeral disk and WhisperX queue. 250 MB ~ 2h
# uncompressed mono WAV; chunked stream uses smaller threshold.
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
MAX_STREAM_CHUNK_BYTES = 8 * 1024 * 1024


def _suffix(filename: str | None) -> str:
    if not filename:
        return ".bin"
    suffix = Path(filename).suffix
    return suffix if suffix else ".bin"


@router.post("")
async def transcribe(
    audio: UploadFile = File(...),
    admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    raw = await audio.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "audio_too_large")
    if not raw:
        raise HTTPException(400, "empty_upload")
    tmp_path = Path(tempfile.gettempdir()) / (
        f"abs-tx-{uuid.uuid4().hex}{_suffix(audio.filename)}"
    )
    try:
        tmp_path.write_bytes(raw)
        result = await transcribe_path(tmp_path)
    except WhisperXUnavailableError as exc:
        logger.warning("whisperx unavailable: %s", exc)
        raise HTTPException(503, f"whisperx_unavailable: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        feature_usage_service.increment(
            "transcribe_meetily", actor_email=admin.get("sub")
        )
    except Exception:
        pass
    return result


@router.post("/stream")
async def transcribe_stream(
    audio: UploadFile = File(...),
    admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    raw = await audio.read()
    if len(raw) > MAX_STREAM_CHUNK_BYTES:
        raise HTTPException(413, "chunk_too_large")
    if not raw:
        raise HTTPException(400, "empty_chunk")
    try:
        result = await transcribe_bytes(
            raw, audio.filename or "chunk.webm", diarize=True
        )
    except WhisperXUnavailableError as exc:
        logger.warning("whisperx stream call failed: %s", exc)
        raise HTTPException(503, f"whisperx_unavailable: {exc}") from exc
    return result
