# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""LangFuse-compatible prompt management with versioning + rollback.

Pre-T-018 we keep prompts in-memory + on disk; once LangFuse SDK fetch is
wired (`langfuse.get_prompt(name, label="production")`), this module switches
to the SDK without changing call sites.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "Prompt",
    "PromptStore",
    "close_prompt_store",
    "get_prompt_store",
]


@dataclass(slots=True)
class Prompt:
    name: str
    text: str
    version: int = 1
    label: str = "production"
    metadata: dict[str, str] = field(default_factory=dict)


class PromptStore:
    def __init__(self, *, jsonl_path: Path | str | None = None) -> None:
        self.path = Path(
            jsonl_path or getattr(settings, "prompt_store_path", "data/prompts.jsonl")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prompts: dict[tuple[str, int], Prompt] = {}
        self._labels: dict[tuple[str, str], int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                p = Prompt(**data)
                self._prompts[(p.name, p.version)] = p
                self._labels[(p.name, p.label)] = p.version
            except Exception as exc:  # noqa: BLE001
                logger.warning("prompt_store_parse_error: %s", exc)

    def _persist(self, prompt: Prompt) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(prompt), ensure_ascii=False) + "\n")

    def create_version(
        self,
        name: str,
        text: str,
        *,
        label: str = "production",
        metadata: dict[str, str] | None = None,
    ) -> Prompt:
        existing = [k for k in self._prompts if k[0] == name]
        next_version = max((v for _, v in existing), default=0) + 1
        prompt = Prompt(
            name=name,
            text=text,
            version=next_version,
            label=label,
            metadata=dict(metadata or {}),
        )
        self._prompts[(name, next_version)] = prompt
        self._labels[(name, label)] = next_version
        self._persist(prompt)
        logger.info("prompt_create name=%s v=%d label=%s", name, next_version, label)
        return prompt

    def get(self, name: str, *, label: str = "production") -> Prompt:
        version = self._labels.get((name, label))
        if version is None:
            raise KeyError(f"prompt {name!r} label={label!r} not found")
        return self._prompts[(name, version)]

    def get_version(self, name: str, version: int) -> Prompt:
        prompt = self._prompts.get((name, version))
        if prompt is None:
            raise KeyError(f"prompt {name!r} v{version} not found")
        return prompt

    def rollback(
        self, name: str, *, to_version: int, label: str = "production"
    ) -> Prompt:
        if (name, to_version) not in self._prompts:
            raise KeyError(f"prompt {name!r} v{to_version} not found for rollback")
        self._labels[(name, label)] = to_version
        self._persist(self._prompts[(name, to_version)])
        logger.info("prompt_rollback name=%s -> v=%d label=%s", name, to_version, label)
        return self._prompts[(name, to_version)]

    def list_versions(self, name: str) -> list[int]:
        return sorted(v for n, v in self._prompts if n == name)

    def close(self) -> None:
        self._prompts.clear()
        self._labels.clear()


_store: PromptStore | None = None


def get_prompt_store() -> PromptStore:
    global _store
    if _store is None:
        _store = PromptStore()
    return _store


def close_prompt_store() -> None:
    global _store
    if _store is None:
        return
    try:
        _store.close()
    finally:
        _store = None
