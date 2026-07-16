# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Live capture (Phase 2) — schedule a meeting link, a bot records it, and the
finished recording flows through the same finalize→Meeting→RAG pipeline an
upload uses.

The honesty rule this file pins: on the default `mock` backend a job is
scheduled but no recording is invented and no Meeting is faked. Only a real
recorder (`local` side-car / `recall`) advances a job to a Meeting — and when it
does, the transcript lands as a genuine, indexed Meeting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.api.auth import current_admin
from app.db.models import CaptureJob, Meeting, MeetingSegment
from app.db.session import get_engine
from app.main import app
from app.meeting import bot_recall, capture_service


# --- helpers -----------------------------------------------------------------


def _transcript_file(tmp_path: Path, *, text: str = "kira her ayın 5'i ödenir") -> Path:
    """A recorder's transcript, in the shape app.services.transcribe returns."""
    payload = {
        "language": "tr",
        "duration_sec": 42.0,
        "speakers": [{"id": "S1", "name": "Speaker 1"}],
        "summary": text[:80],
        "segments": [
            {"speaker_id": "S1", "start": 0.0, "end": 20.0, "text": text},
            {"speaker_id": "S1", "start": 20.0, "end": 42.0, "text": "tamam not aldım"},
        ],
    }
    p = tmp_path / "transcript.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


@pytest.fixture()
def local_backend(tmp_path, monkeypatch):
    """Point the bot at the self-hosted local backend with a private jobs dir,
    and reset the module singleton so it picks that up."""
    from app.config import settings

    jobs = tmp_path / "jobs"
    monkeypatch.setattr(settings, "recall_backend", "local", raising=False)
    monkeypatch.setattr(settings, "meeting_local_runner", "meetily", raising=False)
    monkeypatch.setattr(settings, "meeting_local_jobs_dir", str(jobs), raising=False)
    monkeypatch.setattr(bot_recall, "_singleton", None, raising=False)
    yield jobs
    monkeypatch.setattr(bot_recall, "_singleton", None, raising=False)


@pytest.fixture()
def no_qdrant(monkeypatch):
    """Autoindex is best-effort and hits Qdrant; count the call, touch nothing."""
    calls = {"n": 0}

    def _fake_index(**_kwargs):
        calls["n"] += 1
        return 2

    # ingest.finalize_meeting lazy-imports these from the meetings API module.
    monkeypatch.setattr("app.api.meetings._autoindex_meeting_rag", _fake_index)
    monkeypatch.setattr("app.api.meetings._indexed_chunk_count", lambda m: calls["n"] and 2)
    from app.config import settings

    monkeypatch.setattr(settings, "meeting_rag_autoindex", True, raising=False)
    return calls


@pytest.fixture()
def as_admin():
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _meetings(tenant: str) -> list[Meeting]:
    with Session(get_engine()) as db:
        return list(
            db.exec(select(Meeting).where(Meeting.tenant_slug == tenant)).all()
        )


# --- the honesty rule: mock never fakes a recording --------------------------


def test_mock_backend_schedules_but_never_fakes_a_meeting():
    job = capture_service.create_capture_job(
        tenant_slug="default",
        created_by="admin@local",
        meeting_url="https://meet.google.com/abc-defg-hij",
        title="Weekly sync",
    )
    assert job.status == "scheduled"
    assert job.bot_backend == "mock"
    assert job.meeting_id is None

    # Polling a mock job forever never invents a recording or a Meeting.
    refreshed = capture_service.refresh_status(job)
    assert refreshed.status in {"scheduled", "recording"}
    assert refreshed.meeting_id is None
    assert _meetings("default") == []


def test_bad_url_is_rejected():
    with pytest.raises(ValueError):
        capture_service.create_capture_job(
            tenant_slug="default",
            created_by="admin@local",
            meeting_url="not-a-url",
        )


# --- the real path: a finished recording becomes a Meeting -------------------


def test_completed_recording_becomes_an_indexed_meeting(
    local_backend, no_qdrant, tmp_path
):
    job = capture_service.create_capture_job(
        tenant_slug="acme",
        created_by="admin@acme",
        meeting_url="https://meet.google.com/xyz-1234-abc",
        title="Kickoff",
    )
    assert job.bot_backend == "local"
    assert job.bot_id

    # The side-car records the meeting and writes a transcript, then marks the
    # manifest complete — exactly what refresh_status polls for.
    transcript = _transcript_file(tmp_path)
    from app.meeting.bot_local import transition

    transition(
        job.bot_id,
        status="completed",
        transcript_path=str(transcript),
        jobs_dir=local_backend,
    )

    done = capture_service.refresh_status(job)
    assert done.status == "done"
    assert done.meeting_id is not None
    assert no_qdrant["n"] == 1  # transcript was indexed once

    meetings = _meetings("acme")
    assert len(meetings) == 1
    assert meetings[0].id == done.meeting_id
    assert meetings[0].status == "done"

    with Session(get_engine()) as db:
        segs = list(
            db.exec(
                select(MeetingSegment).where(
                    MeetingSegment.meeting_id == done.meeting_id
                )
            ).all()
        )
    assert len(segs) == 2


def test_completed_without_transcript_stays_honest(local_backend, tmp_path):
    """Recorded, but no transcript on disk yet → holding state, not a Meeting."""
    job = capture_service.create_capture_job(
        tenant_slug="acme",
        created_by="admin@acme",
        meeting_url="https://zoom.us/j/999",
    )
    from app.meeting.bot_local import transition

    transition(job.bot_id, status="completed", jobs_dir=local_backend)
    out = capture_service.refresh_status(job)
    assert out.status == "transcribing"
    assert out.meeting_id is None
    assert _meetings("acme") == []


def test_ingestion_is_idempotent(local_backend, no_qdrant, tmp_path):
    job = capture_service.create_capture_job(
        tenant_slug="acme",
        created_by="admin@acme",
        meeting_url="https://meet.google.com/dup-0000-dup",
    )
    transcript = _transcript_file(tmp_path)
    from app.meeting.bot_local import transition

    transition(
        job.bot_id,
        status="completed",
        transcript_path=str(transcript),
        jobs_dir=local_backend,
    )

    first = capture_service.refresh_status(job)
    # A second poll (e.g. the list endpoint refreshing) must not make a 2nd Meeting.
    second = capture_service.refresh_status(capture_service.get_capture_job(job.job_id))
    assert first.meeting_id == second.meeting_id
    assert len(_meetings("acme")) == 1


# --- the API surface ---------------------------------------------------------


def test_create_list_cancel_via_api(client, as_admin):
    created = client.post(
        "/v1/capture/jobs",
        json={
            "meeting_url": "https://meet.google.com/api-test-001",
            "title": "API sync",
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["platform"] == "meet"
    assert body["recorder_live"] is False  # mock backend — honest

    listed = client.get("/v1/capture/jobs")
    assert listed.status_code == 200
    payload = listed.json()
    assert any(j["job_id"] == body["job_id"] for j in payload["jobs"])
    assert payload["recorder_available"] is False

    cancelled = client.post(f"/v1/capture/jobs/{body['job_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_create_rejects_bad_url_422(client, as_admin):
    r = client.post("/v1/capture/jobs", json={"meeting_url": "ftp://nope"})
    assert r.status_code == 422


def test_get_missing_is_404(client, as_admin):
    r = client.get("/v1/capture/jobs/cap_does_not_exist")
    assert r.status_code == 404


def test_unauthenticated_is_401(client):
    r = client.post(
        "/v1/capture/jobs",
        json={"meeting_url": "https://meet.google.com/x"},
    )
    assert r.status_code == 401
