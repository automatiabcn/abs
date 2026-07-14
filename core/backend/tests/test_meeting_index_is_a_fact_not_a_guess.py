# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""`indexed: true` used to mean "it transcribed", and it was shown as a tick.

The upload path reported `indexed = status == "done" and not quality_note` —
an inference about transcription, printed as a fact about the vector store. The
autoindex that actually writes the chunks is best-effort and swallows its own
failures, so the two could disagree, and when they did the panel showed a green
tick over an empty index. The meeting was simply unanswerable, and nobody found
out until they asked it a question and got a shrug.

Worse, re-uploading the recording — the obvious remedy — did nothing: the dedup
check short-circuits before indexing, so the gap was permanent. That is not a
hypothetical: it is what happened the moment the embedding backend changed, and
every meeting recorded before the change went quiet at once.
"""

from __future__ import annotations

import pytest

import app.api.meetings as meetings_mod
from app.api.auth import current_admin
from app.main import app


@pytest.fixture()
def as_admin():
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_admin, None)


def test_indexed_asks_the_store_instead_of_guessing(monkeypatch):
    """A transcribed meeting whose chunks never landed is not indexed."""

    class _Meeting:
        id = 7
        tenant_slug = "default"
        status = "done"
        quality_note = ""
        # The store files a meeting under the recording's fingerprint, not the
        # row number the database happens to have given it.
        audio_sha256 = "7" * 64

    from app.rag import qdrant_client as qc

    monkeypatch.setattr(
        meetings_mod,
        "_indexed_chunk_count",
        meetings_mod._indexed_chunk_count,  # keep the real one
    )
    monkeypatch.setattr(qc, "count_document", lambda **kw: 0)
    assert meetings_mod._indexed_chunk_count(_Meeting()) == 0

    monkeypatch.setattr(qc, "count_document", lambda **kw: 4)
    assert meetings_mod._indexed_chunk_count(_Meeting()) == 4


def test_chunks_from_a_retired_embedder_do_not_count_as_indexed(monkeypatch):
    """The count is scoped to the model that made the vectors.

    A chunk embedded by yesterday's backend is still sitting in the collection.
    It is present, it is countable, and no query will ever reach it — the
    vectors live in a space nothing searches any more. Counting it as indexed is
    how a corpus goes missing without a single error being raised.
    """
    from app.rag import qdrant_client as qc

    seen = {}

    def _count(*, collection, tenant_id, doc_id, embed_model=None):  # noqa: ANN001
        seen["embed_model"] = embed_model
        return 0

    monkeypatch.setattr(qc, "count_document", _count)

    class _Meeting:
        id = 2
        tenant_slug = "default"
        status = "done"
        quality_note = ""
        audio_sha256 = "2" * 64

    meetings_mod._indexed_chunk_count(_Meeting())
    assert seen["embed_model"], "the count did not say which model it wanted"


def test_a_re_upload_rebuilds_a_missing_index(monkeypatch, client, as_admin):
    """Dedup must not protect the gap as well as the transcript.

    Transcription is the expensive part and is still never repeated. Indexing is
    cheap, checkable, and was the thing that had gone missing — so a duplicate
    upload rebuilds it from the segments already in SQL. Chunk ids are
    deterministic, so a healthy meeting re-indexes to the same points: one
    meeting, one copy.
    """
    import io

    from sqlmodel import Session

    from app.db.models import Meeting, MeetingSegment
    from app.db.session import get_engine
    from app.services import transcribe as transcribe_mod  # noqa: F401

    audio = b"RIFF____WAVEfmt " + b"\x00" * 64
    from app.api.meetings import audio_fingerprint

    with Session(get_engine()) as db:
        row = Meeting(
            tenant_slug="default",
            uploader_email="admin@local",
            filename="standup.wav",
            status="done",
            quality_note="",
            audio_sha256=audio_fingerprint(audio),
            duration_sec=12.0,
            speaker_count=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        db.add(
            MeetingSegment(
                meeting_id=row.id,
                speaker_id="spk_0",
                start_sec=0.0,
                end_sec=5.0,
                text="We ship the new onboarding flow on Friday.",
            )
        )
        db.commit()
        meeting_id = row.id

    calls = {"reindex": 0}

    def _fake_autoindex(*, doc_id, title, uploader_email, result):  # noqa: ANN001
        calls["reindex"] += 1
        calls["segments"] = [s["text"] for s in result["segments"]]
        return len(result["segments"])

    monkeypatch.setattr(meetings_mod, "_autoindex_meeting_rag", _fake_autoindex)
    # The store has nothing for this meeting — the index went missing.
    monkeypatch.setattr(meetings_mod, "_indexed_chunk_count", lambda m: 0)

    resp = client.post(
        "/v1/meetings/upload",
        files={"audio": ("standup.wav", io.BytesIO(audio), "audio/wav")},
    )

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["duplicate_of"] == meeting_id, "the transcript was recomputed"
    assert calls["reindex"] == 1, "the missing index was not rebuilt"
    assert calls["segments"] == ["We ship the new onboarding flow on Friday."]
