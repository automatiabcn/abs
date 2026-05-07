# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Semantic cache — SHA-256 tabanlı LRU + 5dk TTL."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


def prompt_hash(prompt: str, model: str = "") -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class SemanticCache(Generic[T]):
    """In-memory LRU cache. Thread-safe (asyncio.Lock)."""

    def __init__(self, *, max_entries: int = 100, ttl_seconds: float = 300.0) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, _Entry[T]]" = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[T]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at < time.monotonic():
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            self._store[key] = _Entry(
                value=value, expires_at=time.monotonic() + self.ttl_seconds
            )
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        total = self._hits + self._misses
        rate = (self._hits / total * 100) if total else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._store),
            "hit_rate_pct": round(rate, 1),
        }


default_cache: SemanticCache = SemanticCache()
