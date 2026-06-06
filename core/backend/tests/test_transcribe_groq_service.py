"""whisperx-cloud — Groq backend for the async transcribe service client.

Covers `app.services.transcribe`: when `settings.transcribe_backend == "groq"`,
`transcribe_path` / `transcribe_bytes` must hit Groq's OpenAI-compatible audio
endpoint (verbose_json) instead of the local whisperx container, and normalize
the response into the standard `{duration_sec, speakers, segments, summary}`
shape.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services import transcribe as svc


_VERBOSE_JSON = {
    "language": "tr",
    "duration": 8.0,
    "segments": [
        {"start": 0.0, "end": 4.0, "text": " Toplantı başlıyor."},
        {"start": 4.0, "end": 8.0, "text": " Gündem maddeleri şunlar."},
    ],
}


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient capturing the outgoing request."""

    captured: dict = {}

    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a) -> None:
        return None

    async def post(self, url, *, headers=None, data=None, files=None, **kw):
        _FakeAsyncClient.captured = {
            "url": url,
            "headers": headers,
            "data": data,
            "files": files,
        }
        return _FakeResp(_VERBOSE_JSON)


@pytest.fixture
def _groq_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "transcribe_backend", "groq", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "gsk_live", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.captured = {}
    yield


@pytest.mark.asyncio
async def test_transcribe_bytes_uses_groq(_groq_backend) -> None:
    out = await svc.transcribe_bytes(b"audio", "meeting.webm", language="tr")
    assert out["duration_sec"] == 8.0
    assert [s["text"] for s in out["segments"]] == [
        "Toplantı başlıyor.",
        "Gündem maddeleri şunlar.",
    ]
    # No diarization from Groq → single speaker roster.
    assert len(out["speakers"]) == 1
    assert out["summary"]
    cap = _FakeAsyncClient.captured
    assert cap["url"] == svc._GROQ_WHISPER_URL
    assert cap["headers"]["Authorization"] == "Bearer gsk_live"
    assert cap["data"]["response_format"] == "verbose_json"
    assert cap["data"]["language"] == "tr"


@pytest.mark.asyncio
async def test_transcribe_path_uses_groq(tmp_path: Path, _groq_backend) -> None:
    audio = tmp_path / "rec.wav"
    audio.write_bytes(b"RIFFfake")
    out = await svc.transcribe_path(audio, language="tr")
    assert out["duration_sec"] == 8.0
    assert len(out["segments"]) == 2
    # Filename from the path is forwarded to the multipart upload.
    assert _FakeAsyncClient.captured["files"]["file"][0] == "rec.wav"


@pytest.mark.asyncio
async def test_groq_backend_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "transcribe_backend", "groq", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)
    with pytest.raises(svc.WhisperXUnavailableError):
        await svc.transcribe_bytes(b"audio", "x.webm")
