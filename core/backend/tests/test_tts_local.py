"""Coqui XTTS-v2 + Piper free-tier TTS backends."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.meeting import tts_reminder as tts


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(settings, "tts_output_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "voice-x", raising=False)
    tts.close_tts()
    yield
    tts.close_tts()


def test_coqui_backend_unavailable_falls_back_to_piper(tmp_path, monkeypatch):
    """When Coqui isn't installed and auto_fallback=True, switch to Piper."""
    monkeypatch.setattr(settings, "tts_backend", "coqui", raising=False)
    monkeypatch.setattr(settings, "tts_auto_fallback", True, raising=False)

    # Force Coqui to "fail to install" by patching its constructor to raise.
    def _raise_unavailable(self, *args, **kwargs):
        raise tts.TTSBackendUnavailable("coqui not installed")

    # Stub Piper's synthesize to a deterministic file write.
    def _piper_init(self, *, voice_path, voice_id):
        self.voice_id = voice_id

    def _piper_synth(self, text, *, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "stub.wav"
        path.write_bytes(b"piper-stub")
        return tts.ReminderResult(
            audio_path=str(path),
            duration_estimated_s=tts._estimate_seconds(text),
            voice_id=self.voice_id,
            cost_usd=0.0,
            backend="piper",
        )

    with (
        patch.object(tts._CoquiBackend, "synthesize", _raise_unavailable),
        patch.object(tts._CoquiBackend, "__init__", lambda self, **_: None),
        patch.object(tts._PiperBackend, "__init__", _piper_init),
        patch.object(tts._PiperBackend, "synthesize", _piper_synth),
    ):
        reminder = tts.TTSReminder("coqui")
        result = reminder.synthesize(
            "Merhaba ekip, toplantı 14:00", target_dir=tmp_path
        )
        assert result.backend == "piper"
        assert Path(result.audio_path).exists()
        assert reminder.backend == "piper"


def test_coqui_backend_no_fallback_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tts_backend", "coqui", raising=False)
    monkeypatch.setattr(settings, "tts_auto_fallback", False, raising=False)

    def _raise_unavailable(self, *args, **kwargs):
        raise tts.TTSBackendUnavailable("coqui missing")

    with (
        patch.object(tts._CoquiBackend, "__init__", lambda self, **_: None),
        patch.object(tts._CoquiBackend, "synthesize", _raise_unavailable),
    ):
        reminder = tts.TTSReminder("coqui")
        with pytest.raises(tts.TTSBackendUnavailable):
            reminder.synthesize("Merhaba", target_dir=tmp_path)


def test_piper_direct_construct(monkeypatch):
    monkeypatch.setattr(settings, "tts_backend", "piper", raising=False)

    def _piper_init(self, *, voice_path, voice_id):
        self.voice_id = voice_id

    with patch.object(tts._PiperBackend, "__init__", _piper_init):
        reminder = tts.TTSReminder("piper")
        assert reminder.backend == "piper"


def test_unsupported_backend_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        tts.TTSReminder("zoom-tts")


def test_elevenlabs_opt_in_blocked_by_default(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_enabled", False, raising=False)
    with pytest.raises(ValueError, match="opt-in"):
        tts.TTSReminder("elevenlabs")


def test_mock_turkish_text_handled(tmp_path):
    """Free-tier mock backend handles Turkish characters end-to-end."""
    r = tts.TTSReminder("mock").synthesize(
        "İlkbahar geliyor, ağaçlar çiçek açıyor.", target_dir=tmp_path
    )
    assert Path(r.audio_path).exists()
    assert r.cost_usd == 0.0
    assert r.backend == "mock"


def test_mock_backend_no_cost_under_synthetic_load(tmp_path):
    """Run 25 synth calls on the mock and assert zero accumulated cost."""
    reminder = tts.TTSReminder("mock")
    for i in range(25):
        result = reminder.synthesize(f"Hatırlatma {i}", target_dir=tmp_path)
        assert result.cost_usd == 0.0
    assert reminder._spent_usd == 0.0
