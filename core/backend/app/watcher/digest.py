# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""News digest LLM summary (multi-model-ready interface).

Mock summariser concatenates titles. Real LLM call swap-in via the
`summariser` dependency injection at construction time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from app.watcher.sources import NewsItem

logger = logging.getLogger(__name__)

__all__ = ["DigestEntry", "DigestReport", "build_digest", "default_summariser"]


@dataclass(slots=True)
class DigestEntry:
    source: str
    title: str
    url: str
    summary: str
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DigestReport:
    locale: str
    items: list[DigestEntry]
    n_total: int

    def to_markdown(self) -> str:
        lines = ["# ABS Watcher Digest", ""]
        for entry in self.items:
            lines.append(f"## [{entry.title}]({entry.url})")
            lines.append(f"_source: {entry.source}_")
            lines.append("")
            lines.append(entry.summary)
            lines.append("")
        return "\n".join(lines)


def default_summariser(items: list[NewsItem]) -> list[DigestEntry]:
    out: list[DigestEntry] = []
    for item in items:
        first_sentence = item.summary.split(". ")[0]
        out.append(
            DigestEntry(
                source=item.source,
                title=item.title,
                url=item.url,
                summary=first_sentence,
                tags=list(item.tags),
            )
        )
    return out


def build_digest(
    *,
    items: list[NewsItem],
    locale: str = "en",
    summariser: Callable[[list[NewsItem]], list[DigestEntry]] | None = None,
    max_items: int = 25,
) -> DigestReport:
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    summariser = summariser or default_summariser
    capped = items[:max_items]
    entries = summariser(capped)
    logger.info("digest_built locale=%s in=%d out=%d", locale, len(items), len(entries))
    return DigestReport(locale=locale, items=entries, n_total=len(items))
