# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Two questions asked of every recording before it is believed.

**Is this the same audio we already have?** Not "the same filename", not "the
same upload" — the same bytes. A retried upload, a folder synced twice, a
recording attached to two calendar events: each one produces a second meeting
row, a second transcription bill, and a second copy of every passage in the
vector store. The duplicate copies are the expensive part, because retrieval
then returns the same sentence three times and the model reads that as three
sources agreeing.

**Does it contain speech at all?** A two-hour recording whose microphone died
in the first minute does not fail. It transcribes — into a few hundred
characters of confident nonsense hallucinated out of silence and room tone. It
gets stored, indexed, and cited. The tell is not the transcript's content, which
looks fine; it is the *ratio*: two hours of audio that yielded four sentences
was not a quiet meeting, it was a broken one, and the honest move is to keep it
out of the knowledge base and say why.

Both checks are cheap, and both exist because the failure they prevent is
silent — nothing errors, an operator sees a green meeting, and the wrong answer
surfaces weeks later in a chat window with a citation under it.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

# Below this, a recording is too short for the ratio to mean anything: a 30
# second voice note with one sentence in it is a 30 second voice note with one
# sentence in it, not a fault.
MIN_DURATION_FOR_GATE_SEC = 120.0

# A person speaking unhurriedly still produces several hundred characters a
# minute. This floor sits far under any real conversation — it is set to catch
# dead-microphone hallucination, not to judge a sparse meeting.
MIN_CHARS_PER_MINUTE = 40.0

__all__ = [
    "SpeechVerdict",
    "audio_fingerprint",
    "speech_verdict",
]


def audio_fingerprint(payload: bytes) -> str:
    """SHA-256 of the audio itself.

    Bound to the content, never to the filename or the upload id: the whole
    point is to recognise the same recording arriving under a different name.
    """
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SpeechVerdict:
    """Whether a transcript is worth keeping, and why."""

    has_speech: bool
    reason: str  # empty when has_speech is True
    duration_sec: float
    chars: int
    chars_per_minute: float


def _text_of(segment: Any) -> str:
    if isinstance(segment, Mapping):
        return str(segment.get("text") or "")
    return str(getattr(segment, "text", "") or "")


def speech_verdict(duration_sec: float, segments: Iterable[Any]) -> SpeechVerdict:
    """Decide whether this transcript reflects a recording of people talking.

    Accepts either the dicts WhisperX returns or the ORM segment rows — the
    caller has both shapes at different points in the pipeline and neither is
    worth converting for the sake of a ratio.
    """
    duration = max(0.0, float(duration_sec or 0.0))
    chars = sum(len(_text_of(seg).strip()) for seg in segments)
    minutes = duration / 60.0
    density = (chars / minutes) if minutes > 0 else 0.0

    def verdict(has_speech: bool, reason: str = "") -> SpeechVerdict:
        return SpeechVerdict(
            has_speech=has_speech,
            reason=reason,
            duration_sec=duration,
            chars=chars,
            chars_per_minute=round(density, 1),
        )

    if chars == 0:
        # No words at all. True of a silent file and of a failed transcription,
        # and there is nothing to index either way.
        return verdict(False, "No speech was found in this recording.")

    if duration < MIN_DURATION_FOR_GATE_SEC:
        # Too short to reason about density. A short clip with words in it is
        # taken at face value.
        return verdict(True)

    if density < MIN_CHARS_PER_MINUTE:
        return verdict(
            False,
            (
                f"Almost no speech: {_minutes(duration)} of audio produced only "
                f"{chars} characters. The recording is most likely silent — a "
                "microphone that stopped, or the wrong input device — and what "
                "little text came back cannot be trusted, so it was not added "
                "to your knowledge base."
            ),
        )

    return verdict(True)


def _minutes(seconds: float) -> str:
    total = int(seconds // 60)
    if total >= 60:
        hours, rest = divmod(total, 60)
        return f"{hours}h {rest:02d}m"
    return f"{total} minutes"
