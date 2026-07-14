"""Speaker registry tests."""

from __future__ import annotations

import pytest

from app.config import settings
from app.meeting.speaker_match import (
    ConsentRequired,
    SpeakerProfile,
    SpeakerRegistry,
)


def test_enroll_and_identify_roundtrip() -> None:
    reg = SpeakerRegistry()
    p = reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint=b"voiceprint-bytes",
        consent_at="2026-04-28T10:00:00Z",
    )
    found = reg.identify(b"voiceprint-bytes", tenant_id="t1")
    assert found is not None
    assert found.user_id == "alice"
    assert found.fingerprint_hash == p.fingerprint_hash


def test_identify_returns_none_for_unknown_fingerprint() -> None:
    reg = SpeakerRegistry()
    assert reg.identify(b"not-enrolled", tenant_id="t1") is None


def test_identify_blocks_cross_tenant() -> None:
    reg = SpeakerRegistry()
    reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint="abc",
        consent_at="2026-04-28T10:00:00Z",
    )
    assert reg.identify("abc", tenant_id="t2") is None


def test_consent_required_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meeting_voice_consent_required", True, raising=False)
    reg = SpeakerRegistry()
    with pytest.raises(ConsentRequired):
        reg.enroll(
            user_id="bob",
            tenant_id="t1",
            fingerprint="x",
            consent_at="",
        )


def test_consent_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "meeting_voice_consent_required", False, raising=False
    )
    reg = SpeakerRegistry()
    p = reg.enroll(
        user_id="bob",
        tenant_id="t1",
        fingerprint="x",
        consent_at="",
    )
    assert isinstance(p, SpeakerProfile)


def test_forget_removes_profiles() -> None:
    reg = SpeakerRegistry()
    reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint="a",
        consent_at="2026-04-28T10:00:00Z",
    )
    reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint="b",
        consent_at="2026-04-28T10:00:00Z",
    )
    removed = reg.forget(user_id="alice")
    assert removed == 2
    assert reg.identify("a", tenant_id="t1") is None
