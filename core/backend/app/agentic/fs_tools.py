# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Reading files, for an assistant that has been given permission to.

Three tools — list, read, search — and no fourth. Everything they can reach is
whatever ``agent_fs_roots`` names and nothing else; the boundary itself lives in
paths.py, and none of the functions here re-implement any part of it.

The tools return text meant for a model to read, not JSON meant for a machine to
parse: a path with a one-line reason attached ("6 files, 2 folders") is what a
model uses well, and every layer of ceremony between the tool and the answer is
a layer the model can get wrong.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from app.agentic.paths import PathDenied, resolve, roots, within_size

logger = logging.getLogger(__name__)

# A directory with 4,000 files in it is not a listing anyone wants pasted into a
# prompt, and a search that matches everything has told you nothing.
MAX_ENTRIES = 200
MAX_MATCHES = 40
# Anything that is not text is not something to read into a chat. This is a
# convenience, not a defence — paths.py is the defence.
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".log",
    ".sql",
    ".html",
    ".xml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".go",
    ".rs",
    ".java",
    ".rb",
}


def _readable_text(path: Path) -> str:
    """Read a file as text, or say clearly that it is not one.

    Binary files reach this function by being asked for, not by slipping past
    anything; `errors="replace"` would hand the model a page of U+FFFD and let
    it hallucinate meaning into the noise, so a decode failure is reported as a
    fact instead.
    """
    within_size(path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise PathDenied(
            "that file is not text (it looks binary), so there is nothing to read"
        ) from None
    except OSError as exc:
        raise PathDenied(f"cannot read: {exc}") from exc


async def fs_list(path: str = "") -> str:
    """List a folder inside the allowed roots."""
    allowed = roots()
    if not allowed:
        raise PathDenied("file access is not enabled on this server")

    # No path means "what am I allowed to see at all?" — the honest answer to a
    # model that has been told it can read files but not told where.
    if not path.strip():
        lines = ["Folders the assistant may read:"]
        lines.extend(f"  {root}/" for root in allowed)
        return "\n".join(lines)

    target = resolve(path)
    if not target.is_dir():
        return f"{target} is a file, not a folder."

    entries: List[str] = []
    truncated = False
    for index, child in enumerate(sorted(target.iterdir())):
        if index >= MAX_ENTRIES:
            truncated = True
            break
        # A denied child is simply not listed. Naming it — even to refuse it —
        # tells the model that a .env is there and invites a second attempt.
        try:
            resolve(str(child))
        except PathDenied:
            continue
        entries.append(f"  {child.name}/" if child.is_dir() else f"  {child.name}")

    if not entries:
        return f"{target} is empty (or holds nothing the assistant may read)."

    head = f"{target} — {len(entries)} entries"
    if truncated:
        head += f" (first {MAX_ENTRIES}; there are more)"
    return head + "\n" + "\n".join(entries)


async def fs_read(path: str) -> str:
    """Read one text file from inside the allowed roots."""
    target = resolve(path)
    if target.is_dir():
        return f"{target} is a folder. Use fs_list to see what is in it."
    if target.suffix.lower() not in TEXT_SUFFIXES:
        raise PathDenied(
            f"{target.suffix or 'that file type'} is not a text format the "
            "assistant reads"
        )
    return _readable_text(target)


async def fs_search(query: str, path: str = "") -> str:
    """Find which files under a folder contain a string.

    Deliberately a *locator*, not a reader: it returns file paths and the line a
    match sits on, and the model has to call fs_read to see any of it in
    context. A search that returned the surrounding text would be a way to read
    a file's contents one grep at a time, and the size and type limits fs_read
    enforces would never apply.
    """
    if not query.strip():
        raise PathDenied("no search text given")

    allowed = roots()
    if not allowed:
        raise PathDenied("file access is not enabled on this server")

    targets = [resolve(path)] if path.strip() else allowed
    needle = query.lower()
    matches: List[str] = []

    for base in targets:
        if base.is_file():
            candidates = [base]
        else:
            candidates = [p for p in base.rglob("*") if p.is_file()]

        for candidate in candidates:
            if len(matches) >= MAX_MATCHES:
                break
            if candidate.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                resolve(str(candidate))
                within_size(candidate)
                text = candidate.read_text(encoding="utf-8")
            except (PathDenied, UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    matches.append(f"  {candidate}:{number}")
                    break  # one hit per file: this locates, it does not quote

    if not matches:
        return f"No file under the allowed folders contains “{query}”."

    head = f"{len(matches)} file(s) contain “{query}” — use fs_read to open one:"
    if len(matches) >= MAX_MATCHES:
        head = f"First {MAX_MATCHES} files containing “{query}” (there may be more):"
    return head + "\n" + "\n".join(matches)
