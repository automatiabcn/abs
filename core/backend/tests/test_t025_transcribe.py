"""Meeting transcribe dispatcher tests."""

from __future__ import annotations

import pytest

from app.config import settings
from app.meeting import transcribe as t


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "transcribe_backend", "mock", raising=False)
    t.close_transcriber()
    yield
    t.close_transcriber()


def test_mock_backend_parses_speaker_lines() -> None:
    script = """[Ahmet] Müşteri X bugün geldi.
[Ayşe] Kontrat değişikliği talep ediyor.
"""
    out = t.Transcriber("mock").transcribe(script)
    assert out.backend == "mock"
    assert [s.speaker for s in out.segments] == ["Ahmet", "Ayşe"]
    assert out.duration > 0


def test_mock_backend_falls_back_to_speaker_1() -> None:
    out = t.Transcriber("mock").transcribe("orphan line")
    assert out.segments[0].speaker == "speaker_1"


def test_transcript_text_format() -> None:
    out = t.Transcriber("mock").transcribe("[A] hi\n[B] hello")
    assert "[A] hi" in out.text()
    assert "[B] hello" in out.text()


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        t.Transcriber("nope")


def test_deepgram_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepgram_api_key", "", raising=False)
    with pytest.raises(ValueError):
        t.Transcriber("deepgram")


def test_groq_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)
    with pytest.raises(ValueError):
        t.Transcriber("groq")


def test_groq_backend_parses_verbose_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test", raising=False)

    captured: dict = {}

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "language": "tr",
                "duration": 6.5,
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": " Merhaba dünya."},
                    {"start": 3.0, "end": 6.5, "text": " İkinci cümle."},
                ],
            }

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

        def post(self, url, *, headers, data, files):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            captured["files"] = files
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    out = t.Transcriber("groq").transcribe(b"fake-audio-bytes")
    assert out.backend == "groq"
    assert out.language == "tr"
    assert out.duration == 6.5
    assert [s.text for s in out.segments] == ["Merhaba dünya.", "İkinci cümle."]
    assert all(s.speaker == "speaker_1" for s in out.segments)
    assert captured["headers"]["Authorization"] == "Bearer gsk_test"
    assert captured["data"]["response_format"] == "verbose_json"


def test_singleton_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "transcribe_backend", "mock", raising=False)
    t.close_transcriber()
    a = t.get_transcriber()
    b = t.get_transcriber()
    assert a is b
    t.close_transcriber()
    c = t.get_transcriber()
    assert c is not a
