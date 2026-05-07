# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-049 — News watcher source registry + dedupe + rate limit."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitExceeded",
    "NewsItem",
    "Source",
    "WatcherRegistry",
]


class RateLimitExceeded(RuntimeError):
    """Raised when a source's per-minute fetch budget is exhausted."""


@dataclass(slots=True)
class NewsItem:
    source: str
    url: str
    title: str
    published_at: str
    summary: str
    tags: list[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        return hashlib.sha1(
            f"{self.source}|{self.url}|{self.title}".encode("utf-8")
        ).hexdigest()[:16]


@dataclass(slots=True)
class Source:
    name: str
    fetch: Callable[[], list[NewsItem]]
    rate_per_minute: int = 30


class WatcherRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}
        self._buckets: dict[str, tuple[float, int]] = {}
        self._seen: set[str] = set()

    def register(self, source: Source) -> None:
        if source.name in self._sources:
            raise ValueError(f"source {source.name!r} already registered")
        self._sources[source.name] = source

    def fetch_one(self, name: str) -> list[NewsItem]:
        source = self._sources.get(name)
        if source is None:
            raise KeyError(f"source {name!r} not registered")
        now = time.time()
        window_start, used = self._buckets.get(name, (now, 0))
        if now - window_start > 60.0:
            window_start, used = now, 0
        if used + 1 > source.rate_per_minute:
            raise RateLimitExceeded(
                f"source {name!r} hit rate {source.rate_per_minute}/min"
            )
        self._buckets[name] = (window_start, used + 1)

        items = source.fetch()
        out: list[NewsItem] = []
        for item in items:
            fp = item.fingerprint()
            if fp in self._seen:
                continue
            self._seen.add(fp)
            out.append(item)
        logger.info(
            "watcher_fetch source=%s in=%d new=%d", name, len(items), len(out)
        )
        return out

    def fetch_all(self) -> dict[str, list[NewsItem]]:
        return {name: self.fetch_one(name) for name in self._sources}

    def list_sources(self) -> list[str]:
        return sorted(self._sources)
