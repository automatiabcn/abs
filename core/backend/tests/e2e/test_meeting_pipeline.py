"""Meeting pipeline E2E (transcript → action items → tickets → RAG)."""

from __future__ import annotations

from app.meeting.action_items import extract_action_items
from app.meeting.rag_index import (
    MeetingRAGIndexer,
    build_chunks_from_transcript,
)
from app.meeting.speaker_match import SpeakerRegistry
from app.meeting.ticket_link import (
    ExistingTicket,
    link_action_items,
)
from app.meeting.transcribe import Transcriber


SCRIPT = """[Ahmet] Müşteri X yarın aramayı yapacağım.
[Ayşe] Sözleşmeyi gönder.
[Ahmet] Bu hafta raporu hazırla.
[Ayşe] Hava güzel.
"""


def test_full_meeting_pipeline_round_trip() -> None:
    transcript = Transcriber("mock").transcribe(SCRIPT)
    assert len(transcript.segments) == 4
    assert transcript.segments[0].speaker == "Ahmet"

    items = extract_action_items(transcript)
    assert len(items) >= 2
    assignees = {i.assignee for i in items}
    assert {"Ahmet", "Ayşe"} <= assignees

    existing = [ExistingTicket(ticket_id="LIN-1", title="Bu hafta raporu hazırla")]
    decisions = link_action_items(items, existing)
    actions = {d.action for d in decisions}
    assert "create" in actions or "update" in actions

    chunks = build_chunks_from_transcript(
        transcript, meeting_id="m-001", title="Q3 sync", tenant_id="tenant-1"
    )
    assert chunks
    assert all(c["payload"]["tenant_id"] == "tenant-1" for c in chunks)

    upserted: list[int] = []

    def embed(texts):  # noqa: ANN001
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def upsert(*, collection, tenant_id, points):
        upserted.append(len(points))
        return len(points)

    indexer = MeetingRAGIndexer(
        embed_fn=embed, upsert_fn=upsert, ensure_fn=lambda *_: None
    )
    n = indexer.index(
        transcript, meeting_id="m-001", title="Q3 sync", tenant_id="tenant-1"
    )
    assert n == len(transcript.segments)
    assert upserted == [len(transcript.segments)]


def test_speaker_registry_round_trip_for_meeting_speakers() -> None:
    reg = SpeakerRegistry()
    reg.enroll(
        user_id="ahmet@abs.local",
        tenant_id="tenant-1",
        fingerprint=b"ahmet-voice-fp",
        consent_at="2026-04-28T08:00:00Z",
    )
    profile = reg.identify(b"ahmet-voice-fp", tenant_id="tenant-1")
    assert profile is not None
    assert profile.user_id == "ahmet@abs.local"
    assert reg.identify(b"ahmet-voice-fp", tenant_id="tenant-2") is None
