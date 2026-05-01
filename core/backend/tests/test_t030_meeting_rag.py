"""T-030 — Meeting → RAG indexer tests."""

from __future__ import annotations

import pytest

from app.meeting.rag_index import MeetingRAGIndexer, build_chunks_from_transcript
from app.meeting.transcribe import Transcript, TranscriptSegment


def _make() -> Transcript:
    return Transcript(
        language="auto",
        duration=10.0,
        segments=[
            TranscriptSegment(speaker="Ahmet", start=0, end=5, text="Hello world"),
            TranscriptSegment(speaker="Ayşe", start=5, end=10, text="Reply text"),
        ],
        backend="mock",
    )


def test_build_chunks_includes_speaker_prefix() -> None:
    chunks = build_chunks_from_transcript(
        _make(), meeting_id="m1", title="Q3 sync", tenant_id="t1"
    )
    assert len(chunks) == 2
    assert chunks[0]["text"] == "[Ahmet] Hello world"
    assert chunks[0]["payload"]["tenant_id"] == "t1"
    assert chunks[0]["payload"]["kind"] == "meeting_transcript"


def test_build_chunks_skips_empty_segments() -> None:
    t = Transcript(
        language="auto",
        duration=2.0,
        segments=[
            TranscriptSegment(speaker="A", start=0, end=1, text=""),
            TranscriptSegment(speaker="B", start=1, end=2, text="real"),
        ],
        backend="mock",
    )
    chunks = build_chunks_from_transcript(
        t, meeting_id="m2", tenant_id="t1"
    )
    assert len(chunks) == 1
    assert chunks[0]["text"].endswith("real")


def test_indexer_calls_ensure_embed_upsert_in_order() -> None:
    calls: list[str] = []

    def ensure(name):  # noqa: ANN001
        calls.append(f"ensure:{name}")

    def embed(texts):  # noqa: ANN001
        calls.append(f"embed:{len(texts)}")
        return [[0.1, 0.2] for _ in texts]

    def upsert(*, collection, tenant_id, points):
        calls.append(f"upsert:{collection}:{tenant_id}:{len(points)}")
        return len(points)

    n = MeetingRAGIndexer(
        embed_fn=embed,
        upsert_fn=upsert,
        ensure_fn=ensure,
        collection="abs_meetings",
    ).index(_make(), meeting_id="m3", title="t", tenant_id="t1")

    assert n == 2
    assert calls == ["ensure:abs_meetings", "embed:2", "upsert:abs_meetings:t1:2"]


def test_indexer_requires_tenant() -> None:
    with pytest.raises(ValueError):
        MeetingRAGIndexer(
            embed_fn=lambda x: [[0.0]] * len(x),
            upsert_fn=lambda **k: 0,
        ).index(_make(), meeting_id="m4", title="t", tenant_id="")
