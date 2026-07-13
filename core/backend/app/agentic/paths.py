# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Which files the agent may touch, and — mostly — which it may not.

This is the smallest module in the agent and the one most worth reading twice.
Everything the file tools do goes through :func:`resolve`, and every way this
has historically gone wrong is a way :func:`resolve` can be got past.

Three defences, in order:

1. **Canonicalise before deciding.** ``/data/../etc/passwd`` and a symlink at
   ``/data/link -> /etc`` are both requests for a path outside the root, and
   neither looks like one until the path is resolved. We resolve first, then
   decide, and we never touch the caller's string again afterwards.

2. **Compare by segment, not by prefix.** The bug that made this famous shipped
   in Anthropic's own filesystem MCP server: an allowlist of ``/data`` admitted
   ``/data-archived`` and ``/database`` too, because the check was
   ``path.startswith(root)`` and those strings do start with those characters.
   ``Path.is_relative_to`` compares path *components*, which is the question
   actually being asked.

3. **Deny secrets inside the allowlist.** Someone points a root at their project
   folder, and the project folder — as project folders do — has a ``.env`` in it.
   The root is legitimate; the file is not something an assistant should read
   back into a chat transcript that gets stored, indexed and possibly exported.
   A root grants "the documents here", not "everything here".
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Names and suffixes that never leave the machine, regardless of which root they
# sit under. Credentials, keys, and the licence material that would let someone
# mint their own. Matched case-insensitively against the file name; directory
# names are matched against any component of the path.
DENY_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "private.pem",
    "abs.db",
}

DENY_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".keystore"}

DENY_DIRS = {".git", ".ssh", "vault", "keys", "customer-keys", "node_modules"}

# A file the agent will not read into a prompt no matter what it is called: past
# this size it is not a document someone wants summarised, and pulling it into
# the context window would cost more than the answer is worth.
MAX_FILE_BYTES = 512_000


class PathDenied(Exception):
    """The path is outside every root, or inside one but not readable."""


def roots() -> List[Path]:
    """The directories the operator opened up, canonicalised.

    A root that does not exist is dropped rather than raising: a typo in the
    settings should narrow what the agent can reach, never widen it or crash the
    server at boot.
    """
    out: List[Path] = []
    for raw in settings.agent_fs_roots:
        try:
            resolved = Path(raw).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            logger.warning("agent_fs_roots: unusable root ignored: %s", raw)
            continue
        if resolved.is_dir():
            out.append(resolved)
        else:
            logger.warning("agent_fs_roots: not a directory, ignored: %s", raw)
    return out


def _is_denied(path: Path) -> Optional[str]:
    if path.name.lower() in DENY_NAMES:
        return f"{path.name} is not readable"
    if path.suffix.lower() in DENY_SUFFIXES:
        return f"{path.suffix} files are not readable"
    for part in path.parts:
        if part.lower() in DENY_DIRS:
            return f"{part}/ is not readable"
    return None


def resolve(raw: str, *, must_exist: bool = True) -> Path:
    """Turn a model-supplied path into one that is safe to open, or refuse.

    The only way into the filesystem from agent code. Refusals say what was
    refused and why — an agent that gets "denied" with no reason retries the
    same call with a new disguise, which is neither useful nor cheap.
    """
    allowed = roots()
    if not allowed:
        raise PathDenied("file access is not enabled on this server")

    if not raw or not raw.strip():
        raise PathDenied("no path given")

    # `strict=False`: a path that does not exist must still be *checked* — the
    # error we want to return is "outside the allowed folders", not "no such
    # file", and leaking which paths exist outside the roots is itself a small
    # disclosure. Existence is decided after the boundary is.
    try:
        target = Path(raw).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PathDenied(f"unusable path: {exc}") from exc

    inside = next((r for r in allowed if target.is_relative_to(r)), None)
    if inside is None:
        # Deliberately vague about what is out there; specific about the rule.
        raise PathDenied(
            "that path is outside the folders this server allows the assistant to read"
        )

    denied = _is_denied(target.relative_to(inside))
    if denied:
        raise PathDenied(denied)

    if must_exist and not target.exists():
        raise PathDenied("no such file or directory")

    return target


def within_size(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PathDenied(f"cannot stat: {exc}") from exc
    if size > MAX_FILE_BYTES:
        raise PathDenied(
            f"file is {size // 1024} KB; the assistant reads files up to "
            f"{MAX_FILE_BYTES // 1024} KB"
        )
