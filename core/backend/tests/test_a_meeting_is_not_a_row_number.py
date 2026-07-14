# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A meeting was filed in the vector store under the database's row number.

The store outlives the database. Restore last week's backup, or reset a
development install, and the counter starts again over chunks that are still
sitting there — so meeting 2 inherits the chunks of whatever meeting 2 used to
be. The panel shows a green "indexed" tick for a recording it has never indexed,
and a question about that recording is answered out of somebody else's
conversation, with a citation naming the wrong meeting.

The end-to-end suite walked into it the first time it ran twice: a silent
recording — correctly flagged, correctly never indexed — came back marked
`indexed: true`, because an hour earlier a different meeting had held that
number.

The recording's SHA-256 is already computed (it is how the same file uploaded
twice stays one meeting), and it does not restart at 1.
"""

from __future__ import annotations

from app.api.meetings import _doc_id, _legacy_doc_id
from app.db.models import Meeting


def _meeting(**over) -> Meeting:
    return Meeting(
        id=over.pop("id", 2),
        tenant_slug="default",
        uploader_email="admin@abs.local",
        filename="standup.wav",
        audio_sha256=over.pop("audio_sha256", "a" * 64),
        **over,
    )


def test_two_recordings_that_reuse_a_row_number_are_not_the_same_document() -> None:
    # The same id — the backup was restored, the counter came round again — and
    # two entirely different recordings.
    old = _meeting(id=2, audio_sha256="a" * 64)
    new = _meeting(id=2, audio_sha256="b" * 64)

    assert _doc_id(old) != _doc_id(new), (
        "a new meeting was handed the previous meeting's chunks because it "
        "inherited its row number"
    )
    # And the collision that used to be the whole identity is still there,
    # underneath — which is exactly why it cannot be the identity.
    assert _legacy_doc_id(old) == _legacy_doc_id(new)


def test_the_same_recording_is_the_same_document_whatever_its_row_number_is() -> None:
    """The other half: dedup, re-index and re-upload all have to agree."""
    before = _meeting(id=2, audio_sha256="c" * 64)
    after_restore = _meeting(id=77, audio_sha256="c" * 64)
    assert _doc_id(before) == _doc_id(after_restore)


def test_a_recording_with_no_hash_still_has_a_name() -> None:
    """Nothing pre-dating the fingerprint gets dropped on the floor."""
    assert _doc_id(_meeting(id=5, audio_sha256="")) == "meeting-5"


def test_a_silent_recording_never_claims_the_chunks_left_at_its_old_number(
    monkeypatch,
) -> None:
    """The failure as the operator met it.

    Chunks written under `meeting-2` by an earlier install are still in the store.
    A silent recording is uploaded, gets id 2, is flagged, and is never indexed —
    and it must not report itself as indexed on the strength of somebody else's
    chunks. Counting the old number is a kindness we extend to meetings that were
    actually indexed once; a flagged one never was, by construction.
    """
    import app.api.meetings as meetings_mod

    asked: list[str] = []

    def _count(*, collection, tenant_id, doc_id, embed_model=None):  # noqa: ANN001
        asked.append(doc_id)
        return 5 if doc_id == "meeting-2" else 0  # the stranger's chunks

    from app.rag import qdrant_client as qc

    monkeypatch.setattr(qc, "count_document", _count, raising=True)

    silent = _meeting(id=2, audio_sha256="d" * 64, quality_note="no speech detected")
    assert meetings_mod._indexed_chunk_count(silent) == 0, (
        "a recording with no speech in it reported itself indexed, out of chunks "
        "belonging to a different meeting that once had the same row number"
    )
    assert "meeting-2" not in asked

    # A healthy meeting from before the change keeps its tick.
    old_but_real = _meeting(id=2, audio_sha256="", quality_note="")
    assert meetings_mod._indexed_chunk_count(old_but_real) == 5
