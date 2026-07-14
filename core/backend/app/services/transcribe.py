# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.2 — WhisperX (faster-whisper + pyannote diarize) HTTP client.

We use the well-maintained `onerahmet/openai-whisper-asr-webservice` Docker
image which bundles faster-whisper and an ASR HTTP API. Speaker diarization
is layered on top by us — pyannote.audio runs inside the same container via
the `/asr?task=transcribe&diarize=true` toggle the upstream image exposes.

API contract (upstream):
  POST /asr?task=transcribe&diarize=true&output=json
       body=multipart/form-data audio_file=<bytes>
  → 200 application/json {
        "language": "tr",
        "duration": 12.4,
        "segments": [
          {"start": 0.0, "end": 4.2, "text": "...", "speaker": "SPEAKER_00"},
          ...
        ]
      }

Our normalized return:
  {
    "duration_sec": float,
    "speakers": [{"id": "spk_0", "name": "Speaker 1"}, ...],
    "segments": [
      {"speaker_id": "spk_0", "start": float, "end": float, "text": str},
      ...
    ],
    "summary": str,           # heuristic: first 280 chars of joined text
  }
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)


WHISPERX_BASE_URL: Final[str] = os.environ.get(
    "ABS_WHISPERX_URL", "http://whisperx:9000"
)
WHISPERX_TIMEOUT_SECONDS: Final[float] = float(
    os.environ.get("ABS_WHISPERX_TIMEOUT_SECONDS", "180")
)


class WhisperXUnavailableError(RuntimeError):
    pass


def _normalize_speaker(raw: str | None, fallback_idx: int) -> str:
    """`SPEAKER_00` → `spk_0`; missing → `spk_0` (no diarization = one speaker)."""
    if not raw:
        return "spk_0"
    if raw.startswith("SPEAKER_"):
        try:
            n = int(raw.split("_", 1)[1])
            return f"spk_{n}"
        except ValueError:
            return raw
    return raw


def _build_speaker_roster(segments: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    roster: list[dict] = []
    for seg in segments:
        sid = seg["speaker_id"]
        if sid not in seen:
            seen[sid] = len(roster) + 1
            roster.append({"id": sid, "name": f"Speaker {seen[sid]}"})
    return roster


def _summary(segments: list[dict], limit: int = 280) -> str:
    joined = " ".join(s["text"].strip() for s in segments).strip()
    if len(joined) <= limit:
        return joined
    return joined[: limit - 1].rsplit(" ", 1)[0] + "…"


def _parse_response(payload: dict) -> dict[str, Any]:
    raw_segments = payload.get("segments") or []
    segments: list[dict] = []
    for idx, seg in enumerate(raw_segments):
        sid = _normalize_speaker(seg.get("speaker"), idx)
        segments.append(
            {
                "speaker_id": sid,
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": (seg.get("text") or "").strip(),
            }
        )
    duration = float(
        payload.get("duration") or (segments[-1]["end"] if segments else 0.0)
    )
    return {
        "duration_sec": duration,
        "speakers": _build_speaker_roster(segments),
        "segments": segments,
        "summary": _summary(segments),
    }


_GROQ_WHISPER_URL: Final[str] = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_WHISPER_MODEL: Final[str] = os.environ.get(
    "ABS_GROQ_WHISPER_MODEL", "whisper-large-v3"
)


def _transcribe_backend() -> str:
    """Resolve the active backend at call time (settings may be vault-loaded)."""
    try:
        from app.config import settings

        return (getattr(settings, "transcribe_backend", "") or "whisperx").lower()
    except Exception:  # pragma: no cover
        return "whisperx"


async def _transcribe_via_groq(
    audio_bytes: bytes, filename: str, language: str | None
) -> dict[str, Any]:
    """Cloud Whisper via Groq (BYOK) — no local whisperx container / disk / GPU.

    Groq's OpenAI-compatible audio endpoint returns verbose_json with
    `segments` (start/end/text) + `duration`; it does NOT diarize, so every
    segment falls back to a single speaker. Transcript quality is the win;
    speaker labels are a whisperx-only bonus.
    """
    from app.config import settings

    key = (getattr(settings, "groq_api_key", "") or "").strip()
    if not key:
        raise WhisperXUnavailableError(
            "transcribe_backend=groq requires a Groq API key"
        )
    model = (
        getattr(settings, "groq_whisper_model", "") or ""
    ).strip() or _GROQ_WHISPER_MODEL
    data = {"model": model, "response_format": "verbose_json"}
    if language:
        data["language"] = language
    files = {
        "file": (filename or "audio.webm", audio_bytes, "application/octet-stream")
    }
    try:
        async with httpx.AsyncClient(timeout=WHISPERX_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                _GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {key}"},
                data=data,
                files=files,
            )
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("groq whisper call failed: %s", exc)
        raise WhisperXUnavailableError(f"groq_whisper: {exc}") from exc
    try:
        body = resp.json()
    except ValueError as exc:
        raise WhisperXUnavailableError(
            f"groq whisper non-JSON response: {resp.text[:200]}"
        ) from exc
    return _parse_response(body)


async def transcribe_path(
    audio_path: Path,
    diarize: bool = True,
    language: str | None = None,
) -> dict[str, Any]:
    """Upload `audio_path` to WhisperX and return the normalized payload."""
    if _transcribe_backend() == "groq":
        return await _transcribe_via_groq(
            audio_path.read_bytes(), audio_path.name, language
        )
    params = {
        "task": "transcribe",
        "output": "json",
        "diarize": "true" if diarize else "false",
    }
    if language:
        params["language"] = language

    try:
        with audio_path.open("rb") as fh:
            files = {
                "audio_file": (
                    audio_path.name,
                    fh.read(),
                    "application/octet-stream",
                )
            }
        async with httpx.AsyncClient(
            base_url=WHISPERX_BASE_URL, timeout=WHISPERX_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post("/asr", params=params, files=files)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
        logger.warning("whisperx call failed: %s", exc)
        raise WhisperXUnavailableError(str(exc)) from exc

    try:
        body = resp.json()
    except ValueError as exc:
        raise WhisperXUnavailableError(
            f"whisperx non-JSON response: {resp.text[:200]}"
        ) from exc
    return _parse_response(body)


async def transcribe_bytes(
    audio_bytes: bytes,
    filename: str,
    diarize: bool = True,
    language: str | None = None,
) -> dict[str, Any]:
    """In-memory variant for streaming chunks (no temp file)."""
    if _transcribe_backend() == "groq":
        return await _transcribe_via_groq(audio_bytes, filename, language)
    params = {
        "task": "transcribe",
        "output": "json",
        "diarize": "true" if diarize else "false",
    }
    if language:
        params["language"] = language
    files = {
        "audio_file": (filename, audio_bytes, "application/octet-stream"),
    }
    try:
        async with httpx.AsyncClient(
            base_url=WHISPERX_BASE_URL, timeout=WHISPERX_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post("/asr", params=params, files=files)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("whisperx call failed (chunk): %s", exc)
        raise WhisperXUnavailableError(str(exc)) from exc
    try:
        return _parse_response(resp.json())
    except ValueError as exc:
        raise WhisperXUnavailableError(
            f"whisperx non-JSON response: {resp.text[:200]}"
        ) from exc
