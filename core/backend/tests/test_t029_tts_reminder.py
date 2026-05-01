"""T-029 — TTS reminder tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.meeting import tts_reminder as tts


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "tts_backend", "mock", raising=False)
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "voice-x", raising=False)
    monkeypatch.setattr(settings, "tts_output_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "elevenlabs_budget_usd", 50.0, raising=False)
    tts.close_tts()
    yield
    tts.close_tts()


def test_synthesize_returns_audio_path(tmp_path: Path) -> None:
    r = tts.TTSReminder("mock").synthesize("kısa hatırlatma", target_dir=tmp_path)
    assert Path(r.audio_path).exists()
    assert r.voice_id == "voice-x"
    assert r.duration_estimated_s > 0
    # T-F02 — free tier: mock backend has zero cost.
    assert r.cost_usd == 0.0


def test_budget_only_enforced_for_paid_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T-F02 — budget gate only fires for opt-in ElevenLabs, not free backends."""
    monkeypatch.setattr(settings, "elevenlabs_budget_usd", 0.000001, raising=False)
    # Mock (free) is unaffected by budget caps now.
    r = tts.TTSReminder("mock").synthesize("Some long text here for sure", target_dir=tmp_path)
    assert r.backend == "mock"
    assert r.cost_usd == 0.0


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        tts.TTSReminder("nope")


def test_elevenlabs_requires_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-F02 — ElevenLabs is now opt-in via ABS_ELEVENLABS_ENABLED."""
    monkeypatch.setattr(settings, "elevenlabs_enabled", False, raising=False)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "anything", raising=False)
    with pytest.raises(ValueError, match="opt-in"):
        tts.TTSReminder("elevenlabs")


def test_elevenlabs_requires_api_key_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "elevenlabs_enabled", True, raising=False)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "", raising=False)
    with pytest.raises(ValueError):
        tts.TTSReminder("elevenlabs")


def test_singleton_lifecycle() -> None:
    a = tts.get_tts()
    b = tts.get_tts()
    assert a is b
    tts.close_tts()
    c = tts.get_tts()
    assert c is not a
