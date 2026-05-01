"""T-025 — Meeting transcribe dispatcher tests."""

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


def test_singleton_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "transcribe_backend", "mock", raising=False)
    t.close_transcriber()
    a = t.get_transcriber()
    b = t.get_transcriber()
    assert a is b
    t.close_transcriber()
    c = t.get_transcriber()
    assert c is not a
