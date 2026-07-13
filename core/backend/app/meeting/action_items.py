# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Action item extractor — verb/date heuristics behind an LLM-ready interface.

Hints cover the supported product languages; non-ASCII words are written as
escapes so the source stays ASCII while matching the same terms."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.meeting.transcribe import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

__all__ = ["ActionItem", "extract_action_items"]


@dataclass(slots=True)
class ActionItem:
    text: str
    assignee: str | None
    due_date: str | None
    source_segment: int  # index into transcript.segments


_VERB_HINTS = (
    "yapaca\u011f\u0131m", "yapmal\u0131", "haz\u0131rla", "g\u00f6nder", "ara", "topla",
    "investigate", "ship", "draft", "send", "schedule", "follow up",
    "ensure", "fix", "deliver", "review", "kontrol",
)
_DUE_HINTS = (
    (r"yar\u0131n", "tomorrow"),
    (r"bu hafta", "this_week"),
    (r"gelecek hafta", "next_week"),
    (r"by friday", "friday"),
    (r"end of month", "eom"),
    (r"next monday", "next_monday"),
)


def _is_action(text: str) -> bool:
    lowered = text.lower()
    return any(h in lowered for h in _VERB_HINTS)


def _detect_due(text: str) -> str | None:
    lowered = text.lower()
    for pattern, label in _DUE_HINTS:
        if re.search(pattern, lowered):
            return label
    return None


def extract_action_items(transcript: Transcript) -> list[ActionItem]:
    items: list[ActionItem] = []
    for idx, seg in enumerate(transcript.segments):
        if _is_action(seg.text):
            items.append(
                ActionItem(
                    text=seg.text.strip(),
                    assignee=seg.speaker,
                    due_date=_detect_due(seg.text),
                    source_segment=idx,
                )
            )
    logger.debug(
        "action_items_extracted n=%d total_segments=%d",
        len(items),
        len(transcript.segments),
    )
    return items
