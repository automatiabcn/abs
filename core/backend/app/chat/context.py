# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What the developer chose to send with a chat question.

Retrieval picks files by relevance; this module handles the ones the
developer named — `@app/routes.py` in the question, a file added from the
picker — and the project's own rules file. Both go through the same
exclusions and secret redaction as retrieved files: naming a file is not a
way to send a credential.
"""

from __future__ import annotations

import os
from typing import List, Sequence, Tuple

#: Where a project keeps standing instructions for the assistant. First
#: match wins; the file is read whole, capped, and shown to the model as
#: rules it must follow.
RULES_FILES: Tuple[str, ...] = (".abs/rules.md", "AGENTS.md", ".abs/AGENTS.md")
RULES_MAX_CHARS = 4000
PINNED_MAX_CHARS = 12000
PINNED_MAX_FILES = 8


def _inside(base: str, rel: str) -> str | None:
    """The absolute path for a workspace-relative one, or None if it escapes."""
    rel = rel.replace("\\", "/").lstrip("./") if rel.startswith("./") else rel
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    full = os.path.realpath(os.path.join(base, rel))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


def pinned_files(root: str, rels: Sequence[str]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Read the files the developer named. Returns (files, refused) where
    `refused` lists the ones that were not sent and why — a named file that
    silently goes missing is the failure the panel exists to prevent."""
    from app.context.exclusions import IgnoreMatcher, excluded_reason, redact_secrets

    base = os.path.realpath(root)
    ignore = IgnoreMatcher(base)
    out: List[Tuple[str, str]] = []
    refused: List[str] = []
    spent = 0
    for rel in list(dict.fromkeys(r.strip() for r in rels if r and r.strip()))[:PINNED_MAX_FILES]:
        full = _inside(base, rel)
        if full is None:
            refused.append(f"{rel}: outside the project")
            continue
        why = excluded_reason(rel, ignore)
        if why is not None:
            refused.append(f"{rel}: {why}")
            continue
        try:
            with open(full, "r", encoding="utf-8") as fh:
                body = fh.read(PINNED_MAX_CHARS)
        except (OSError, UnicodeDecodeError):
            refused.append(f"{rel}: not readable as text")
            continue
        body, _n = redact_secrets(body)
        if spent + len(body) > PINNED_MAX_CHARS:
            body = body[: max(0, PINNED_MAX_CHARS - spent)]
        if not body:
            refused.append(f"{rel}: no room left")
            continue
        spent += len(body)
        out.append((rel, body))
    return out, refused


def project_rules(root: str) -> Tuple[str, str]:
    """(rules text, which file) for the project, or ("", "")."""
    base = os.path.realpath(root)
    for rel in RULES_FILES:
        full = _inside(base, rel)
        if not full or not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8") as fh:
                text = fh.read(RULES_MAX_CHARS + 1)
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) > RULES_MAX_CHARS:
            text = text[:RULES_MAX_CHARS] + "\n[... rules file truncated ...]"
        return text.strip(), rel
    return "", ""
