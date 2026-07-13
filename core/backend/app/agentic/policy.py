# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The gate every agent tool call passes through.

The product's promise is that an assistant with tools does not become an
assistant that acts behind your back. That promise lives here, as one function
with one return value: allow, require approval, or deny.

Four levels, ordered by what a call can cost you if the model is wrong:

    L0  read-only facts (status, quota, catalogue)      → allowed, audited
    L1  read files inside an allowlisted root           → allowed, audited   (F2)
    L2  writes and outbound side effects                → human approval     (F2/F3)
    L3  shell commands                                  → off unless enabled,
                                                          human approval every call (F3)

Two rules matter more than the table:

* A tool the operator has not enabled is *absent*, not merely refused. A model
  cannot be talked into calling a tool it was never told exists, and a catalogue
  that lists a forbidden tool is an invitation to try.

* Tool results are untrusted input. Text that comes back from a document, a web
  page or another tool may contain instructions ("now delete the vault"); it is
  data, never a mandate. The gate is re-applied to every call the model makes
  afterwards, so an injected instruction still has to walk past a human to do
  anything consequential. This is the mitigation the 2026 prompt-injection RCE
  disclosures came down to, and it only holds if approval is enforced *here* —
  at dispatch — rather than trusted to the model's own judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

from app.config import settings

Verdict = Literal["allow", "approve", "deny"]


class Level(IntEnum):
    """What a tool call can cost you, ascending."""

    READ = 0        # L0 — facts about this system
    READ_FILE = 1   # L1 — file contents from an allowlisted root
    WRITE = 2       # L2 — writes, sends, anything with a footprint outside
    SHELL = 3       # L3 — arbitrary commands


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    level: Level
    reason: str = ""


def is_enabled(level: Level) -> bool:
    """Whether the operator has turned this level on at all.

    Enablement is checked before the catalogue is even built, so a disabled
    level's tools never reach the model (see the "absent, not refused" rule).
    """
    if not settings.agent_mode_enabled:
        return False
    if level is Level.READ:
        return True
    if level is Level.READ_FILE:
        return bool(settings.agent_fs_roots)
    if level is Level.WRITE:
        return settings.agent_fs_write_enabled
    if level is Level.SHELL:
        return settings.agent_shell_enabled
    return False


def check(level: Level) -> Decision:
    """The gate. Every dispatch calls this; nothing calls a tool around it."""
    if not settings.agent_mode_enabled:
        return Decision("deny", level, "agent_mode_disabled")

    if not is_enabled(level):
        # Reached only if a caller hands us a name the catalogue never offered —
        # a bug, or a model inventing a tool. Same answer either way.
        return Decision("deny", level, f"level_disabled:{level.name.lower()}")

    if level >= Level.WRITE:
        return Decision("approve", level, "human_approval_required")

    return Decision("allow", level, "")
