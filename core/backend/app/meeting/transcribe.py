"""T-025 — Meeting transcribe + diarization dispatcher.

Default backend "mock" produces deterministic segments from a script string
so unit tests don't need WhisperX/pyannote. Real backends are gated behind
deferred imports.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "TranscriptSegment",
    "Transcript",
    "Transcriber",
    "close_transcriber",
    "get_transcriber",
]


@dataclass(slots=True)
class TranscriptSegment:
    speaker: str
    start: float
    end: float
    text: str


@dataclass(slots=True)
class Transcript:
    language: str
    duration: float
    segments: list[TranscriptSegment]
    backend: str

    def text(self) -> str:
        return "\n".join(f"[{s.speaker}] {s.text}" for s in self.segments)


class _MockBackend:
    """Parses lines like `[speaker] text` into segments."""

    def __init__(self) -> None:
        logger.info("transcribe_mock_init")

    def transcribe(self, audio: bytes | str | Path) -> Transcript:
        if isinstance(audio, (bytes, Path)):
            text = (
                audio.decode("utf-8", errors="replace")
                if isinstance(audio, bytes)
                else Path(audio).read_text("utf-8")
            )
        else:
            text = audio

        segments: list[TranscriptSegment] = []
        cursor = 0.0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\[(?P<sp>[^\]]+)\]\s*(?P<txt>.*)$", line)
            if m:
                speaker = m.group("sp")
                content = m.group("txt")
            else:
                speaker = "speaker_1"
                content = line
            duration = max(1.0, len(content) / 12.0)
            segments.append(
                TranscriptSegment(
                    speaker=speaker,
                    start=cursor,
                    end=cursor + duration,
                    text=content,
                )
            )
            cursor += duration
        return Transcript(
            language="auto",
            duration=cursor,
            segments=segments,
            backend="mock",
        )


class _WhisperXBackend:
    """T-Q03 — local WhisperX model (GPU-bound, deferred import).

    `whisperx.load_model` is heavy; we cache the loaded model on the instance.
    Caller receives the same Transcript shape as the mock backend.
    """

    def __init__(self, *, device: str = "cuda") -> None:
        try:
            import whisperx  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "whisperx backend requires `pip install whisperx`"
            ) from exc
        self.device = device
        self._model: object | None = None
        logger.info("transcribe_whisperx_init device=%s", device)

    def _load(self) -> object:
        if self._model is None:
            import whisperx

            model_name = getattr(settings, "whisperx_model", "small")
            compute_type = "float16" if self.device == "cuda" else "int8"
            self._model = whisperx.load_model(
                model_name, device=self.device, compute_type=compute_type
            )
        return self._model

    def transcribe(self, audio_path: bytes | str | Path) -> Transcript:
        import whisperx

        if isinstance(audio_path, bytes):
            raise ValueError("whisperx backend requires a file path, not bytes")
        path = str(audio_path)
        audio = whisperx.load_audio(path)
        result = self._load().transcribe(audio, batch_size=16)  # type: ignore[attr-defined]
        segments: list[TranscriptSegment] = []
        duration = 0.0
        for seg in result.get("segments", []):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            duration = max(duration, end)
            segments.append(
                TranscriptSegment(
                    speaker=str(seg.get("speaker", "speaker_1")),
                    start=start,
                    end=end,
                    text=str(seg.get("text", "")).strip(),
                )
            )
        return Transcript(
            language=str(result.get("language", "auto")),
            duration=duration,
            segments=segments,
            backend="whisperx",
        )


class _DeepgramBackend:
    """T-Q03 — Deepgram /v1/listen REST client (httpx)."""

    BASE_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise ValueError("deepgram backend requires settings.deepgram_api_key")
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError("deepgram backend requires httpx") from exc
        self.api_key = api_key
        logger.info("transcribe_deepgram_init")

    def transcribe(self, audio_path: bytes | str | Path) -> Transcript:
        import httpx

        if isinstance(audio_path, (str, Path)):
            data = Path(audio_path).read_bytes()
        else:
            data = audio_path
        params = {
            "model": getattr(settings, "deepgram_model", "nova-2"),
            "diarize": "true",
            "punctuate": "true",
            "smart_format": "true",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
        }
        with httpx.Client(timeout=120.0) as client:
            r = client.post(self.BASE_URL, params=params, headers=headers, content=data)
            r.raise_for_status()
            payload = r.json()

        results = payload.get("results", {})
        channel = (results.get("channels") or [{}])[0]
        alt = (channel.get("alternatives") or [{}])[0]
        segments: list[TranscriptSegment] = []
        duration = float(payload.get("metadata", {}).get("duration", 0.0))
        for word in alt.get("words", []):
            speaker = f"speaker_{int(word.get('speaker', 0))}"
            segments.append(
                TranscriptSegment(
                    speaker=speaker,
                    start=float(word.get("start", 0.0)),
                    end=float(word.get("end", 0.0)),
                    text=str(word.get("punctuated_word") or word.get("word", "")),
                )
            )
        return Transcript(
            language=str(payload.get("metadata", {}).get("language", "auto")),
            duration=duration,
            segments=segments,
            backend="deepgram",
        )


class Transcriber:
    backend: str

    def __init__(self, backend_name: str | None = None) -> None:
        backend = backend_name or getattr(settings, "transcribe_backend", "mock") or "mock"
        self.backend = backend
        if backend == "mock":
            self._impl = _MockBackend()
        elif backend == "whisperx":
            self._impl = _WhisperXBackend(
                device=getattr(settings, "transcribe_device", "cuda")
            )
        elif backend == "deepgram":
            self._impl = _DeepgramBackend(
                api_key=getattr(settings, "deepgram_api_key", "") or "",
            )
        else:
            raise ValueError(f"unsupported transcribe backend: {backend}")

    def transcribe(self, audio: bytes | str | Path) -> Transcript:
        out = self._impl.transcribe(audio)
        out.backend = self.backend
        logger.debug(
            "transcribe backend=%s duration=%.1f segments=%d",
            self.backend,
            out.duration,
            len(out.segments),
        )
        return out

    def close(self) -> None:
        return None


_singleton: Transcriber | None = None


def get_transcriber() -> Transcriber:
    global _singleton
    if _singleton is None:
        _singleton = Transcriber()
    return _singleton


def close_transcriber() -> None:
    global _singleton
    if _singleton is None:
        return
    try:
        _singleton.close()
    finally:
        _singleton = None
