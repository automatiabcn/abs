"""S20.1 — Minimal HTTP wrapper around `piper-tts`.

Endpoints:
  GET  /health           liveness probe (returns 200 once first model is loaded
                         OR if the warm-up voice is configured to lazy-load).
  GET  /api/voices       list of installed voice IDs (filenames in /models).
  POST /api/tts          {"text": str, "voice": str} -> audio/wav PCM16.

Voices are downloaded on demand from the rhasspy mirror (huggingface.co/rhasspy/piper-voices).
Mount /models as a persistent volume so the first hit doesn't repeat.

License: MIT (Piper) — attribution in docs/legal/THIRD_PARTY_LICENSES.md.
"""

from __future__ import annotations

import io
import logging
import os
import urllib.request
import wave
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from piper.voice import PiperVoice
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piper-server")

MODEL_DIR = Path(os.environ.get("ABS_PIPER_MODEL_DIR", "/models")).resolve(strict=False)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Only filenames matching this regex are allowed to be
# composed into MODEL_DIR. Defends against path-traversal even though
# VOICE_INDEX is a closed allowlist (defense-in-depth).
_VOICE_ID_RE = __import__("re").compile(r"^[A-Za-z0-9_-]+$")

VOICE_INDEX: Dict[str, str] = {
    "tr_TR-fettah-medium": "tr/tr_TR/fettah/medium",
    "en_US-amy-medium": "en/en_US/amy/medium",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium",
}


def _safe_model_path(voice_id: str, suffix: str) -> Path:
    """Compose a model filename onto MODEL_DIR, rejecting traversal/symlinks."""
    if not _VOICE_ID_RE.match(voice_id):
        raise HTTPException(400, f"invalid voice id: {voice_id}")
    candidate = (MODEL_DIR / f"{voice_id}{suffix}").resolve(strict=False)
    try:
        candidate.relative_to(MODEL_DIR)
    except ValueError as exc:
        raise HTTPException(400, "voice path outside MODEL_DIR") from exc
    if candidate.is_symlink():
        # `resolve(strict=False)` already canonicalizes; reject explicit symlinks.
        raise HTTPException(400, "voice path is a symlink")
    return candidate
# Piper-voices uses a tagged ref (`v1.0.0`) for stable downloads; `main` is
# blocked from Hugging Face's CDN raw resolver for these blobs.
VOICE_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
)


def _ensure_voice(voice_id: str) -> Path:
    if voice_id not in VOICE_INDEX:
        raise HTTPException(400, f"unknown voice: {voice_id}")
    onnx = _safe_model_path(voice_id, ".onnx")
    cfg = _safe_model_path(voice_id, ".onnx.json")
    if onnx.exists() and cfg.exists():
        return onnx
    rel = VOICE_INDEX[voice_id]
    for url, target in (
        (f"{VOICE_BASE}/{rel}/{voice_id}.onnx", onnx),
        (f"{VOICE_BASE}/{rel}/{voice_id}.onnx.json", cfg),
    ):
        if target.exists():
            continue
        logger.info("downloading %s -> %s", url, target)
        # URL is computed from the closed VOICE_INDEX allowlist + a fixed base.
        with urllib.request.urlopen(url, timeout=120) as resp:  # nosec B310
            target.write_bytes(resp.read())
    return onnx


_VOICE_CACHE: Dict[str, PiperVoice] = {}


def _voice(voice_id: str) -> PiperVoice:
    if voice_id in _VOICE_CACHE:
        return _VOICE_CACHE[voice_id]
    onnx = _ensure_voice(voice_id)
    voice = PiperVoice.load(str(onnx))
    _VOICE_CACHE[voice_id] = voice
    return voice


app = FastAPI(title="ABS Piper TTS", version="1.0.0")


class SynthBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = "tr_TR-fettah-medium"


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "voices_installed": sorted(p.stem for p in MODEL_DIR.glob("*.onnx")),
    }


@app.get("/api/voices")
async def list_voices() -> dict:
    installed = sorted(p.stem for p in MODEL_DIR.glob("*.onnx"))
    return {"installed": installed, "available": list(VOICE_INDEX.keys())}


@app.post("/api/tts")
async def tts(body: SynthBody) -> Response:
    try:
        voice = _voice(body.voice)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("voice load failed")
        raise HTTPException(503, f"voice_load_failed: {exc}") from exc

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        voice.synthesize(body.text, wav_file)
    return Response(content=buf.getvalue(), media_type="audio/wav")
