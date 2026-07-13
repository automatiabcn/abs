"""T-F01 — local meeting bot + manual upload + WER<10% pipeline."""

from __future__ import annotations

import pathlib

import pytest

from app.meeting.bot_local import (
    LocalMeetingBackend,
    LocalRunnerError,
    SUPPORTED_RUNNERS,
    transition,
)
from app.meeting.bot_recall import MeetingBot
from app.meeting.upload_manual import (
    ALLOWED_EXTENSIONS,
    UploadError,
    accept_upload,
    google_calendar_pickup_stub,
    wer,
)


def _backend(tmp_path: pathlib.Path) -> LocalMeetingBackend:
    return LocalMeetingBackend(jobs_dir=tmp_path)


def test_local_backend_schedules_writes_manifest(tmp_path):
    backend = _backend(tmp_path)
    job = backend.schedule(
        meeting_url="https://meet.example/room/123",
        tenant_id="acme",
    )
    assert job.bot_id
    assert job.estimated_cost_usd == 0.0
    manifest_path = tmp_path / f"{job.bot_id}.json"
    assert manifest_path.exists()


def test_local_backend_status_roundtrip(tmp_path):
    backend = _backend(tmp_path)
    job = backend.schedule(meeting_url="https://meet/x", tenant_id="acme")
    fetched = backend.status(job.bot_id)
    assert fetched.bot_id == job.bot_id
    assert fetched.tenant_id == "acme"
    assert fetched.metadata["runner"] in SUPPORTED_RUNNERS


def test_local_backend_status_unknown_id(tmp_path):
    with pytest.raises(KeyError):
        _backend(tmp_path).status("does-not-exist")


def test_local_backend_cancel(tmp_path):
    backend = _backend(tmp_path)
    job = backend.schedule(meeting_url="https://meet/x", tenant_id="acme")
    backend.cancel(job.bot_id)
    with pytest.raises(KeyError):
        backend.status(job.bot_id)


def test_transition_marks_complete(tmp_path):
    backend = _backend(tmp_path)
    job = backend.schedule(meeting_url="https://meet/x", tenant_id="acme")
    final = transition(
        job.bot_id,
        status="completed",
        transcript_path="/tmp/x.txt",
        jobs_dir=tmp_path,
    )
    assert final.status == "completed"
    assert final.transcript_path == "/tmp/x.txt"


def test_unsupported_runner_rejected(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "meeting_local_runner", "zoom-bot", raising=False)
    with pytest.raises(LocalRunnerError):
        LocalMeetingBackend()


def test_meetingbot_default_recall_now_opt_in_only():
    """Direct backend='recall' without ABS_RECALL_ENABLED must raise."""
    with pytest.raises(ValueError, match="opt-in"):
        MeetingBot("recall")


def test_meetingbot_local_backend_constructs(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "meeting_local_jobs_dir", str(tmp_path), raising=False
    )
    bot = MeetingBot("local")
    assert bot.backend == "local"


def test_upload_rejects_unknown_extension():
    with pytest.raises(UploadError):
        accept_upload(
            tenant_id="acme",
            filename="malware.exe",
            payload=b"x",
        )


def test_upload_rejects_empty_payload():
    with pytest.raises(UploadError):
        accept_upload(tenant_id="acme", filename="x.wav", payload=b"")


def test_upload_persists_and_transcribes(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "meeting_recordings_dir", str(tmp_path / "rec"), raising=False
    )
    monkeypatch.setattr(
        settings, "meeting_local_jobs_dir", str(tmp_path / "jobs"), raising=False
    )
    monkeypatch.setattr(settings, "transcribe_backend", "mock", raising=False)
    payload = b"[esra] hello team\n[mert] yes hi\n"
    job, transcript = accept_upload(
        tenant_id="acme",
        filename="sync.wav",
        payload=payload,
        jobs_dir=tmp_path / "jobs",
    )
    assert job.status == "completed"
    assert job.transcript_path is not None
    assert any("hello team" in seg.text for seg in transcript.segments)


def test_allowed_extensions_includes_common_audio():
    for ext in (".mp3", ".mp4", ".wav"):
        assert ext in ALLOWED_EXTENSIONS


def test_wer_identical_strings_zero():
    assert wer("the quick brown fox", "the quick brown fox") == 0.0


def test_wer_under_threshold_for_similar_text():
    ref = (
        "the quick brown fox jumps over the lazy dog and meets the team at noon "
        "to discuss the quarterly plan"
    )
    hyp = (
        "the quick brown fox jumps over the lazy dog and meets the team at noon "
        "to discuss the quarterly plan"
    ).replace("noon", "noon today")  # 1 substitution-ish
    assert wer(ref, hyp) < 0.10


def test_wer_high_for_unrelated_text():
    assert wer("good morning everyone", "completely different sentence here") > 0.5


def test_google_calendar_pickup_creates_jobs(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "meeting_local_jobs_dir", str(tmp_path), raising=False
    )
    events = [
        {
            "id": "evt-1",
            "tenant_id": "acme",
            "hangoutLink": "https://meet.example/abc",
            "summary": "Q3 sync",
        },
        {"id": "evt-skip", "tenant_id": "acme", "summary": "no link"},
    ]
    out = google_calendar_pickup_stub(events)
    assert len(out) == 1
    assert out[0]["calendar_event_id"] == "evt-1"
    assert out[0]["meeting_url"].startswith("https://meet.example")
