# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Which project the caller has open.

The first thing a tester said after installing (2026-08-03): they connected a
provider, opened a project, asked the chat about it, and got an answer that had
nothing to do with their code. They were right, and it was not a chat bug — of
the thirty-three tools the editor calls, exactly one sent the workspace. Opening
a project made Composer project-aware and left everything else answering from
general knowledge.

The obvious repair — add `workspace_root` to every signature — is thirty-three
edits, and every tool added afterwards starts out wrong again until somebody
remembers. So the editor states the workspace once, here, and any tool that
wants it asks. A tool written next month gets it by asking, not by being
remembered.

Kept in memory on purpose. This is a fact about a live editor session, not
something to write to a customer's disk: it is worthless after a restart, the
editor re-states it on activation, and a path is the kind of thing that should
not outlive the window it came from.
"""

from __future__ import annotations

import os
import threading
from typing import Dict, Optional, Tuple

_LOCK = threading.Lock()
# One slot per (tenant, user, client). The client is the editor window: a
# developer with two windows open — the ordinary case — has two projects open,
# and until 2026-08-18 they shared one slot, so the 60-second heartbeat of
# whichever window spoke last decided which project the OTHER window's chat
# answered about (audit: a question about ws-audit was answered from
# RobotMarket's files, `used_files` and all).
_OPEN: Dict[Tuple[str, str, str], str] = {}
# The most recent slot per (tenant, user): what an older editor that sends no
# client id, or a tool call that names no root, falls back to.
_LATEST: Dict[Tuple[str, str], str] = {}


def _key(tenant: str, user: str, client: str = "") -> Tuple[str, str, str]:
    return (tenant or "default", user or "", client or "")


def _validated(root: str) -> Optional[str]:
    try:
        resolved = os.path.realpath(root)
    except OSError:
        return None
    if not os.path.isdir(resolved):
        return None
    return resolved


def set_workspace(
    tenant: str, user: str, root: str, client_id: str = ""
) -> Optional[str]:
    """Record the project this caller (this editor window) has open.

    An empty root clears that window's slot — the editor saying "no folder
    open", and it has to be possible to say. A path that is not a directory
    is refused rather than stored: a stale or invented root would make every
    tool that trusts this quietly answer about nothing.
    """
    with _LOCK:
        if not root:
            gone = _OPEN.pop(_key(tenant, user, client_id), None)
            uk = _key(tenant, user)[:2]
            if gone is not None and _LATEST.get(uk) == gone:
                # The latest slot closed; another live window (if any) is now
                # the fallback — never a closed project.
                remaining = [v for k, v in _OPEN.items() if k[:2] == uk]
                if remaining:
                    _LATEST[uk] = remaining[-1]
                else:
                    _LATEST.pop(uk, None)
            elif not any(k[:2] == uk for k in _OPEN):
                _LATEST.pop(uk, None)
            return None
        resolved = _validated(root)
        if resolved is None:
            return None
        _OPEN[_key(tenant, user, client_id)] = resolved
        _LATEST[_key(tenant, user)[:2]] = resolved
        return resolved


def current_workspace(
    tenant: str,
    user: str,
    client_id: str = "",
    explicit_root: str = "",
) -> Optional[str]:
    """The project this caller has open, or None.

    Precedence: a root the call itself names (the editor knows which window
    is asking; the server does not) → this client's slot → the most recently
    announced slot for the user (older editors). None means "no project", not
    "use the server's own directory" — a tool that fell back to the process's
    cwd would answer about our container's filesystem, which is worse than
    admitting it does not know.
    """
    if explicit_root:
        return _validated(explicit_root)
    with _LOCK:
        root = None
        if client_id:
            root = _OPEN.get(_key(tenant, user, client_id))
        if not root:
            root = _LATEST.get(_key(tenant, user)[:2])
    if root and os.path.isdir(root):
        return root
    return None


def problem_with_root(root: str) -> Optional[str]:
    """Why `root` cannot be used as a project, in a sentence, or None if it can.

    The rule in `current_workspace` above — an absent project is not the
    server's own directory — was written for the tools that *ask* for the open
    workspace. The tools that are *handed* one never applied it.

    The editor sends `workspaceFolders?.[0]?.uri.fsPath ?? ""`, and that `??`
    is reached every time somebody opens the window without a folder: a fresh
    install, a single file, the state the first run is in. Python resolves ""
    to the process's working directory, so `composer_propose` and
    `code_graph_build` were reading the server's own source — 200 files of it,
    measured 2026-08-05 — and would have sent it to the customer's provider as
    the context for a request, then proposed edits against paths inside it.

    Absolute is required rather than merely "is a directory", because "." and
    "relative/path" are directories too, just not the customer's.
    """
    if not root or not root.strip():
        return "no folder is open — open the project folder you want to work on"
    if not os.path.isabs(root):
        return (
            f"a project has to be an absolute path; {root!r} is relative and "
            f"would be read against the server's own directory"
        )
    if not os.path.isdir(root):
        return f"the server cannot see a directory at {root!r}"
    return None


def forget(tenant: str, user: str) -> None:
    """Drop every slot this user has — all windows. Test and sign-out helper."""
    uk = _key(tenant, user)[:2]
    with _LOCK:
        for k in [k for k in _OPEN if k[:2] == uk]:
            _OPEN.pop(k, None)
        _LATEST.pop(uk, None)
