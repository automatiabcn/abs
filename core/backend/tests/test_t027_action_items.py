"""T-027 — Action item extractor tests."""

from __future__ import annotations

from app.meeting.action_items import extract_action_items
from app.meeting.transcribe import Transcript, TranscriptSegment


def _make(segments: list[tuple[str, str]]) -> Transcript:
    return Transcript(
        language="auto",
        duration=float(len(segments)),
        segments=[
            TranscriptSegment(speaker=sp, start=i, end=i + 1, text=tx)
            for i, (sp, tx) in enumerate(segments)
        ],
        backend="mock",
    )


def test_extracts_action_with_assignee_and_no_due() -> None:
    t = _make([("Ahmet", "Müşteri ile yarın aramayı yapacağım.")])
    items = extract_action_items(t)
    assert len(items) == 1
    assert items[0].assignee == "Ahmet"
    assert items[0].due_date == "tomorrow"
    assert items[0].source_segment == 0


def test_no_action_when_segment_is_pure_chitchat() -> None:
    t = _make([("Ayşe", "Merhaba, bugün hava güzel.")])
    assert extract_action_items(t) == []


def test_multiple_actions_preserve_order() -> None:
    t = _make(
        [
            ("Ahmet", "Sözleşmeyi gönder."),
            ("Ayşe", "Hava güzel."),
            ("Ahmet", "By Friday I'll send the report."),
        ]
    )
    items = extract_action_items(t)
    assert [i.source_segment for i in items] == [0, 2]
    assert items[1].due_date == "friday"


def test_english_action_phrases_detected() -> None:
    t = _make([("Bob", "I'll draft the proposal end of month.")])
    items = extract_action_items(t)
    assert len(items) == 1
    assert items[0].due_date == "eom"


def test_assignee_is_speaker_field() -> None:
    t = _make([("Carol", "Schedule a sync tomorrow.")])
    items = extract_action_items(t)
    assert items[0].assignee == "Carol"
