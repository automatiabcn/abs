# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Path-injection canonicalization helper.

CodeQL `py/path-injection` flagged 8 sinks in core/backend/app/symbols/* and
infra/piper/server.py. This module enforces ALLOWED_ROOTS canonicalization
before any file is opened; symlinks and `..`-traversal are rejected.

`ALLOWED_ROOTS` is computed at import time so prod containers can opt-in via
`ABS_SYMBOLS_ALLOWED_ROOTS` (`:`-separated absolute paths). Defaults are
permissive enough for local dev (project cwd) but block /etc, /root, /proc.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Tuple


def _resolve_roots() -> Tuple[Path, ...]:
    raw = os.environ.get("ABS_SYMBOLS_ALLOWED_ROOTS", "").strip()
    if raw:
        roots = tuple(Path(p).resolve(strict=False) for p in raw.split(":") if p)
        if roots:
            return roots
    # Defaults: project tree (cwd) and explicit data dir.
    cwd = Path.cwd().resolve(strict=False)
    extra = (
        Path("/app").resolve(strict=False),
        Path("/app/data").resolve(strict=False),
        Path("/tmp").resolve(strict=False),
        Path("/models").resolve(strict=False),
        Path("/var/folders").resolve(strict=False),  # macOS pytest tmp_path
    )
    return (cwd, *extra)


ALLOWED_ROOTS: Tuple[Path, ...] = _resolve_roots()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_resolve(
    user_path: str | os.PathLike[str], *, roots: Iterable[Path] | None = None
) -> Path:
    """Canonicalize and assert the path lives inside an allowed root.

    Raises PermissionError if the resolved path escapes ALLOWED_ROOTS or is a
    symlink pointing outside. Existence is not enforced (callers may probe
    optional artefacts); use `safe_open_text` when a file MUST exist.
    """
    candidates = tuple(roots) if roots is not None else ALLOWED_ROOTS
    resolved = Path(user_path).resolve(strict=False)
    # Reject symlinks pointing to a location outside roots.
    if Path(user_path).is_symlink():
        link_target = Path(user_path).resolve(strict=True)
        if not any(_is_within(link_target, root) for root in candidates):
            raise PermissionError(f"symlink target outside allowed roots: {user_path}")
    if not any(_is_within(resolved, root) for root in candidates):
        raise PermissionError(f"path outside allowed roots: {user_path}")
    return resolved


def safe_read_text(
    user_path: str | os.PathLike[str],
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> str:
    """Read text with ALLOWED_ROOTS enforcement. Raises FileNotFoundError if missing."""
    p = safe_resolve(user_path)
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_text(encoding=encoding, errors=errors)


__all__ = ["ALLOWED_ROOTS", "safe_resolve", "safe_read_text"]
