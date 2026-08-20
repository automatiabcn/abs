# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Where a project may be — the one gate every path-taking tool goes through.

Five MCP tools accept a directory from the caller: composer_propose,
code_graph_build, workspace_set, rag_index, sandbox_run. Until 2026-08-18
each checked "absolute and exists" and nothing else, so any token could
point them at the server's own state directory (an audit read `.env` with
the session secret out of `sandbox_run`'s stdout), at `/etc`, or at another
tenant's mount. The repository had already pulled `apply_patch` off the MCP
surface for exactly this reason and left the other five doors open.

Rules, in order:

1. **Never** the filesystem root, system trees, or the user's home directory
   itself (a project lives *in* a home directory, it is not one).
2. **Never** the server's own data directory (`settings.data_dir` and the
   process cwd when it holds the state) — that is where keys and the DB are.
3. If the operator set `ABS_WORKSPACE_ROOTS` (`:`-separated, `{tenant}`
   allowed as a placeholder), the project must be under one of them; on a
   hosted server that is the tenant's mount and nothing else.
4. Otherwise (a laptop, the ordinary install) any other directory is fine.

The reason is a sentence for the developer, not a code.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

_ALWAYS_FORBIDDEN_PREFIXES = (
    "/etc", "/private/etc", "/proc", "/sys", "/dev", "/root", "/boot",
    "/bin", "/sbin", "/usr", "/lib", "/lib64", "/var/root", "/var/db",
    "/System", "/Library", "/private/var/root", "/private/var/db",
    "/Windows", "/Program Files", "/Program Files (x86)",
)
_ALWAYS_FORBIDDEN_EXACT = ("/", "/private", "/var", "/private/var", "/tmp", "/private/tmp", "/home", "/Users", "/opt")


def _real(p: str) -> str:
    try:
        return os.path.realpath(p)
    except OSError:
        return p


def _under(child: str, parent: str) -> bool:
    child = child.rstrip("/") or "/"
    parent = parent.rstrip("/") or "/"
    return child == parent or child.startswith(parent + "/")


def configured_roots(tenant: str = "") -> List[str]:
    raw = os.environ.get("ABS_WORKSPACE_ROOTS", "").strip()
    if not raw:
        return []
    out: List[str] = []
    for part in raw.split(":"):
        part = part.strip()
        if not part:
            continue
        if "{tenant}" in part:
            if not tenant:
                continue
            part = part.replace("{tenant}", tenant)
        out.append(_real(part))
    return out


def _server_state_dirs() -> Iterable[str]:
    dirs: List[str] = []
    try:
        from app.config import settings

        d = str(getattr(settings, "data_dir", "") or "")
        if d:
            dirs.append(_real(d))
            # The e2e/dev layout keeps state one level up from data_dir; a
            # directory holding the server's own .env is state too.
            parent = os.path.dirname(_real(d))
            if parent and os.path.exists(os.path.join(parent, ".env")):
                dirs.append(parent)
    except Exception:  # noqa: BLE001
        pass
    cwd = _real(os.getcwd())
    if os.path.exists(os.path.join(cwd, ".env")) or os.path.exists(
        os.path.join(cwd, "setup_state.json")
    ):
        dirs.append(cwd)
    return dirs


def forbidden_reason(root: str, tenant: str = "") -> Optional[str]:
    """Why `root` may not be a project for `tenant` — or None when it may.

    Assumes the caller has already required an absolute, existing directory
    (`problem_with_root` does); this is only about WHERE.
    """
    real = _real(root)
    if real in _ALWAYS_FORBIDDEN_EXACT:
        return f"{root!r} is not a project — it is a system directory"
    for pfx in _ALWAYS_FORBIDDEN_PREFIXES:
        if _under(real, pfx):
            return f"{root!r} is inside {pfx}, which is never a project"
    home = _real(os.path.expanduser("~"))
    if home and home != "/" and real == home:
        return "the home directory itself is not a project — open the folder inside it"
    for state in _server_state_dirs():
        if _under(real, state):
            return "that is the server's own data directory, not a project"
    allowed = configured_roots(tenant)
    if allowed and not any(_under(real, a) for a in allowed):
        return (
            "this server only serves projects under its configured workspace "
            "roots; ask the operator to mount the project there"
        )
    return None


def within(path: str, root: str) -> bool:
    """Is `path` (a file the model named) inside `root`? Realpath both, so a
    symlink out of the project is 'outside'."""
    return _under(_real(path), _real(root))
