# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""TTS reminder dispatcher (free-tier refactor).

Backends:
  - mock      — deterministic file-write for unit tests (default).
  - coqui     — Coqui XTTS-v2 local synthesis (GPU 8GB recommended). Free.
  - piper     — Piper TTS CPU fallback. Free.
  - elevenlabs— PAID, opt-in only via `ABS_ELEVENLABS_ENABLED=true`.

Free path is `coqui` → `piper` (auto-fallback when GPU/Coqui unavailable).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ReminderResult",
    "TTSBudgetExceeded",
    "TTSBackendUnavailable",
    "TTSReminder",
    "close_tts",
    "get_tts",
]


class TTSBudgetExceeded(RuntimeError):
    """Raised when the cumulative cost would exceed the configured budget."""


class TTSBackendUnavailable(RuntimeError):
    """Raised when a free backend's library / model is not installed."""


@dataclass(slots=True)
class ReminderResult:
    audio_path: str
    duration_estimated_s: float
    voice_id: str
    cost_usd: float
    backend: str = "mock"


def _estimate_seconds(text: str) -> float:
    # ~150 WPM at default speed.
    words = max(1, len(text.split()))
    return words / 2.5


def _estimate_cost_eleven(seconds: float) -> float:
    # ElevenLabs Multilingual v2 ~ $0.0006 / character; approx via secs.
    return 0.0006 * seconds * 18.0


class _MockBackend:
    name = "mock"

    def __init__(self, *, voice_id: str) -> None:
        self.voice_id = voice_id
        logger.info("tts_mock_init voice=%s", voice_id)

    def synthesize(self, text: str, *, target_dir: Path) -> ReminderResult:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"reminder_{uuid.uuid4().hex[:8]}.wav"
        path.write_bytes(b"RIFF....WAVEfmt ....mock-tts....data....")
        duration = _estimate_seconds(text)
        return ReminderResult(
            audio_path=str(path),
            duration_estimated_s=duration,
            voice_id=self.voice_id,
            cost_usd=0.0,
            backend=self.name,
        )


class _CoquiBackend:
    """Coqui XTTS-v2 local synthesis. Deferred import.

    Requires: `pip install TTS` and an XTTS-v2 model at `coqui_model_path`.
    Speaker cloning: `coqui_speaker_wav` (30s reference).
    """

    name = "coqui"

    def __init__(
        self, *, model_path: str, voice_id: str, speaker_wav: str | None
    ) -> None:
        try:
            from TTS.api import TTS  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover — env-dependent
            raise TTSBackendUnavailable(
                "coqui backend requires `pip install TTS` and an XTTS-v2 model"
            ) from exc
        self._TTS = TTS
        self.model_path = model_path
        self.voice_id = voice_id
        self.speaker_wav = speaker_wav
        self._tts: object | None = None
        logger.info("tts_coqui_init model=%s voice=%s", model_path, voice_id)

    def _load(self) -> object:  # pragma: no cover — heavyweight
        if self._tts is None:
            self._tts = self._TTS(self.model_path)
        return self._tts

    def synthesize(
        self, text: str, *, target_dir: Path
    ) -> ReminderResult:  # pragma: no cover
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"reminder_{uuid.uuid4().hex[:8]}.wav"
        kwargs: dict = {"text": text, "file_path": str(path), "language": "tr"}
        if self.speaker_wav:
            kwargs["speaker_wav"] = self.speaker_wav
        self._load().tts_to_file(**kwargs)  # type: ignore[attr-defined]
        return ReminderResult(
            audio_path=str(path),
            duration_estimated_s=_estimate_seconds(text),
            voice_id=self.voice_id,
            cost_usd=0.0,
            backend=self.name,
        )


class _PiperBackend:
    """Piper TTS CPU fallback. Deferred import.

    Requires: `pip install piper-tts` and a `.onnx` voice at `piper_voice_path`.
    """

    name = "piper"

    def __init__(self, *, voice_path: str, voice_id: str) -> None:
        try:
            from piper.voice import PiperVoice  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover — env-dependent
            raise TTSBackendUnavailable(
                "piper backend requires `pip install piper-tts` and a Piper voice"
            ) from exc
        self._PiperVoice = PiperVoice
        self.voice_path = voice_path
        self.voice_id = voice_id
        self._voice: object | None = None
        logger.info("tts_piper_init voice=%s", voice_path)

    def _load(self) -> object:  # pragma: no cover — heavyweight
        if self._voice is None:
            self._voice = self._PiperVoice.load(self.voice_path)
        return self._voice

    def synthesize(
        self, text: str, *, target_dir: Path
    ) -> ReminderResult:  # pragma: no cover
        import wave

        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"reminder_{uuid.uuid4().hex[:8]}.wav"
        with wave.open(str(path), "wb") as fh:
            self._load().synthesize(text, fh)  # type: ignore[attr-defined]
        return ReminderResult(
            audio_path=str(path),
            duration_estimated_s=_estimate_seconds(text),
            voice_id=self.voice_id,
            cost_usd=0.0,
            backend=self.name,
        )


class _ElevenLabsBackend:
    """Opt-in ElevenLabs Multilingual v2 REST client (httpx)."""

    name = "elevenlabs"
    BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, *, api_key: str, voice_id: str) -> None:
        if not api_key:
            raise ValueError("elevenlabs backend requires settings.elevenlabs_api_key")
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError("elevenlabs backend requires httpx") from exc
        self.api_key = api_key
        self.voice_id = voice_id

    def synthesize(self, text: str, *, target_dir: Path) -> ReminderResult:
        import httpx

        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"reminder_{uuid.uuid4().hex[:8]}.mp3"
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        headers = {
            "xi-api-key": self.api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{self.BASE_URL}/{self.voice_id}",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            path.write_bytes(r.content)
        duration = _estimate_seconds(text)
        return ReminderResult(
            audio_path=str(path),
            duration_estimated_s=duration,
            voice_id=self.voice_id,
            cost_usd=_estimate_cost_eleven(duration),
            backend=self.name,
        )


class TTSReminder:
    backend: str

    def __init__(self, backend_name: str | None = None) -> None:
        backend = backend_name or getattr(settings, "tts_backend", "mock") or "mock"
        self.backend = backend
        voice_id = getattr(settings, "elevenlabs_voice_id", "") or "default"
        if backend == "mock":
            self._impl: object = _MockBackend(voice_id=voice_id)
        elif backend == "coqui":
            self._impl = _CoquiBackend(
                model_path=getattr(settings, "coqui_model_path", "") or "",
                voice_id=voice_id,
                speaker_wav=getattr(settings, "coqui_speaker_wav", "") or None,
            )
        elif backend == "piper":
            self._impl = _PiperBackend(
                voice_path=getattr(settings, "piper_voice_path", "") or "",
                voice_id=voice_id,
            )
        elif backend == "elevenlabs":
            if not bool(getattr(settings, "elevenlabs_enabled", False)):
                raise ValueError(
                    "ElevenLabs backend is opt-in; set ABS_ELEVENLABS_ENABLED=true to use it"
                )
            self._impl = _ElevenLabsBackend(
                api_key=getattr(settings, "elevenlabs_api_key", "") or "",
                voice_id=voice_id,
            )
        else:
            raise ValueError(f"unsupported tts backend: {backend}")
        self._spent_usd = 0.0
        self._spent_window_start = time.time()

    def synthesize(
        self, text: str, *, target_dir: Path | str | None = None
    ) -> ReminderResult:
        if time.time() - self._spent_window_start > 30 * 86400:
            self._spent_usd = 0.0
            self._spent_window_start = time.time()

        seconds = _estimate_seconds(text)
        # Only ElevenLabs has a real cost; free backends short-circuit.
        if self.backend == "elevenlabs":
            cost = _estimate_cost_eleven(seconds)
            budget = float(getattr(settings, "elevenlabs_budget_usd", 50.0))
            if self._spent_usd + cost > budget:
                raise TTSBudgetExceeded(
                    f"budget ${budget:.2f} would be breached "
                    f"(spent ${self._spent_usd:.2f} + new ${cost:.2f})"
                )

        target = Path(target_dir or getattr(settings, "tts_output_dir", "data/tts"))
        try:
            result = self._impl.synthesize(text, target_dir=target)  # type: ignore[attr-defined]
        except TTSBackendUnavailable:
            # Coqui → Piper auto-fallback when GPU/Coqui not present.
            if self.backend == "coqui" and getattr(settings, "tts_auto_fallback", True):
                logger.warning("tts_coqui_unavailable_falling_back_to_piper")
                self._impl = _PiperBackend(
                    voice_path=getattr(settings, "piper_voice_path", "") or "",
                    voice_id=getattr(settings, "elevenlabs_voice_id", "") or "default",
                )
                self.backend = "piper"
                result = self._impl.synthesize(text, target_dir=target)  # type: ignore[attr-defined]
            else:
                raise

        self._spent_usd += result.cost_usd
        if result.duration_estimated_s > 30.0:
            logger.warning(
                "tts_reminder_long duration=%.1fs voice=%s backend=%s",
                result.duration_estimated_s,
                result.voice_id,
                result.backend,
            )
        return result

    def close(self) -> None:
        return None


_singleton: TTSReminder | None = None


def get_tts() -> TTSReminder:
    global _singleton
    if _singleton is None:
        _singleton = TTSReminder()
    return _singleton


def close_tts() -> None:
    global _singleton
    if _singleton is None:
        return
    try:
        _singleton.close()
    finally:
        _singleton = None
