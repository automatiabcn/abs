# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The two ways a meeting upload succeeds and is still wrong.

Neither of these failures raises anything. A duplicate upload returns 201 and a
green meeting; a two-hour recording of silence returns 201 and a green meeting.
Both then quietly poison retrieval — the first by putting the same passage in
the store three times so it reads as three sources agreeing, the second by
indexing sentences the model hallucinated over room tone. The tests are what
makes those two paths visible, because nothing else in the pipeline complains.
"""

from __future__ import annotations

import io

import pytest

from app.api.auth import current_admin
from app.main import app
from app.meeting.quality import audio_fingerprint, speech_verdict


@pytest.fixture()
def as_admin():
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _wav(marker: bytes = b"speech") -> tuple[str, io.BytesIO, str]:
    return ("meeting.wav", io.BytesIO(b"RIFF" + marker), "audio/wav")


def _transcript(*, duration: float, text: str):
    return {
        "duration_sec": duration,
        "speakers": ["speaker_1"],
        "summary": text[:80],
        "segments": [
            {"speaker_id": "speaker_1", "start": 0.0, "end": 5.0, "text": text}
        ],
    }


# --- the ratio, in isolation -------------------------------------------------


class TestSpeechVerdict:
    def test_two_hours_of_near_silence_is_not_a_meeting(self):
        # The exact shape of the failure: a long recording, a short transcript,
        # nothing that errored. 538 characters over two hours is a dead mic.
        verdict = speech_verdict(7200.0, [{"text": "x" * 538}])
        assert verdict.has_speech is False
        assert "microphone" in verdict.reason

    def test_a_real_conversation_passes(self):
        # ~900 chars/minute — an ordinary talking pace, nowhere near the floor.
        segments = [{"text": "We agreed to ship on Friday. " * 60}]
        verdict = speech_verdict(1800.0, segments)
        assert verdict.has_speech is True
        assert verdict.reason == ""

    def test_a_short_clip_is_taken_at_face_value(self):
        # 20 seconds with one sentence in it is a voice note, not a fault. The
        # density check would flag it, so the gate must not apply below the
        # duration floor.
        verdict = speech_verdict(20.0, [{"text": "Approved, go ahead."}])
        assert verdict.has_speech is True

    def test_no_words_at_all_is_refused_at_any_length(self):
        verdict = speech_verdict(15.0, [])
        assert verdict.has_speech is False
        assert verdict.chars == 0

    def test_it_reads_orm_rows_as_well_as_dicts(self):
        class Row:
            text = "y" * 100

        assert speech_verdict(7200.0, [Row()]).has_speech is False


class TestFingerprint:
    def test_the_same_bytes_under_another_name_have_the_same_fingerprint(self):
        assert audio_fingerprint(b"\x00audio") == audio_fingerprint(b"\x00audio")

    def test_different_audio_does_not_collide(self):
        assert audio_fingerprint(b"one") != audio_fingerprint(b"two")


# --- the endpoint ------------------------------------------------------------


class TestUpload:
    def test_the_same_recording_twice_is_one_meeting(
        self, client, as_admin, monkeypatch
    ):
        import app.api.meetings as meetings

        calls = {"transcribe": 0, "index": 0}
        # A stand-in for the vector store, so "is it indexed?" is answered by
        # what was actually written rather than by what we hoped happened. The
        # re-upload path checks this before deciding whether to rebuild.
        store = {"chunks": 0}

        async def fake_transcribe(path):
            calls["transcribe"] += 1
            return _transcript(
                duration=600.0, text="We agreed to ship on Friday. " * 40
            )

        def fake_index(**kwargs):
            calls["index"] += 1
            store["chunks"] = 3
            return 3

        monkeypatch.setattr(meetings, "transcribe_path", fake_transcribe)
        monkeypatch.setattr(meetings, "_autoindex_meeting_rag", fake_index)
        monkeypatch.setattr(meetings, "_indexed_chunk_count", lambda m: store["chunks"])
        monkeypatch.setattr(meetings.settings, "meeting_rag_autoindex", True)

        first = client.post("/v1/meetings/upload", files={"audio": _wav()})
        assert first.status_code == 201, first.text
        assert first.json().get("duplicate_of") is None

        # Same bytes, different filename — a re-sync, a retried upload.
        again = client.post(
            "/v1/meetings/upload",
            files={
                "audio": ("copy-of-meeting.wav", io.BytesIO(b"RIFFspeech"), "audio/wav")
            },
        )
        assert again.status_code == 201, again.text
        assert again.json()["duplicate_of"] == first.json()["id"]
        assert again.json()["id"] == first.json()["id"]

        # Transcription — the expensive half — ran exactly once: no second GPU
        # minute. And the meeting was indexed once, because the first index
        # worked; a re-upload rebuilds the index only when it is genuinely
        # missing, which is what makes a broken index fixable at all.
        assert calls == {"transcribe": 1, "index": 1}

    def test_a_silent_recording_is_kept_but_never_indexed(
        self, client, as_admin, monkeypatch
    ):
        import app.api.meetings as meetings

        indexed = {"n": 0}

        async def fake_transcribe(path):
            # Two hours in, a few hundred characters out. Exactly what WhisperX
            # returns for a recording whose microphone died: confident, fluent,
            # and invented.
            return _transcript(
                duration=7200.0, text="Thank you. Thank you very much." * 8
            )

        def fake_index(**kwargs):
            indexed["n"] += 1
            return 5

        monkeypatch.setattr(meetings, "transcribe_path", fake_transcribe)
        monkeypatch.setattr(meetings, "_autoindex_meeting_rag", fake_index)
        monkeypatch.setattr(meetings.settings, "meeting_rag_autoindex", True)

        r = client.post(
            "/v1/meetings/upload",
            files={"audio": ("silent.wav", io.BytesIO(b"RIFFsilence"), "audio/wav")},
        )
        assert r.status_code == 201, r.text
        body = r.json()

        assert indexed["n"] == 0  # nothing hallucinated reached the vector store
        assert body["indexed"] is False
        assert body["quality_note"]  # and the operator is told why, in words
        assert "silent" in body["quality_note"]
        # The transcript is still there to look at — the claim is "we did not
        # trust this", not "we threw it away".
        assert body["segments"]

    def test_a_real_meeting_is_indexed_and_carries_no_warning(
        self, client, as_admin, monkeypatch
    ):
        import app.api.meetings as meetings

        indexed = {"n": 0}
        store = {"chunks": 0}

        async def fake_transcribe(path):
            return _transcript(
                duration=1800.0, text="We agreed to ship on Friday. " * 60
            )

        def fake_index(**kwargs):
            indexed["n"] += 1
            store["chunks"] = 7
            return 7

        monkeypatch.setattr(meetings, "transcribe_path", fake_transcribe)
        monkeypatch.setattr(meetings, "_autoindex_meeting_rag", fake_index)
        # `indexed` is now read back from the store, not inferred from the fact
        # that transcription finished — the two used to be conflated, and a
        # meeting with an empty index still showed a green tick.
        monkeypatch.setattr(meetings, "_indexed_chunk_count", lambda m: store["chunks"])
        monkeypatch.setattr(meetings.settings, "meeting_rag_autoindex", True)

        r = client.post(
            "/v1/meetings/upload",
            files={
                "audio": ("standup.wav", io.BytesIO(b"RIFFreal-standup"), "audio/wav")
            },
        )
        body = r.json()

        assert indexed["n"] == 1
        assert body["indexed"] is True
        assert body["quality_note"] == ""
