# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What the assistant is currently allowed to do, stated plainly.

Read-only, and deliberately so. The obvious product move is to let an admin add
a folder from the Settings page — and it is the wrong move: the panel's admin is
a tenant role, the filesystem is the *host*, and a text field that writes
`agent_fs_roots` is a text field where someone types `/` and reads the server's
own secrets back through a chat window. Which folders exist and which of them an
assistant may see is a decision that belongs to whoever installs the server, in
`.env`, next to the database password.

So the panel shows the answer instead of setting it: here is what is on, here is
what is off, here is exactly which folders were opened up. An operator who wants
a different answer edits ABS_AGENT_FS_ROOTS and restarts, which is a slower loop
on purpose — it is the same loop as changing any other trust boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agentic import dispatcher
from app.agentic.paths import roots
from app.agentic.policy import Level, is_enabled
from app.api.auth import current_admin
from app.config import settings

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.get("/capabilities")
async def capabilities(_admin: dict = Depends(current_admin)) -> dict:
    return {
        "enabled": settings.agent_mode_enabled,
        "max_steps": settings.agent_max_steps,
        # The four levels, as the operator's switches left them.
        "can_read_system": is_enabled(Level.READ),
        "can_read_files": is_enabled(Level.READ_FILE),
        "can_write_files": is_enabled(Level.WRITE),
        "can_run_commands": is_enabled(Level.SHELL),
        # The folders, resolved — an unusable root is dropped by roots(), so
        # this is what the assistant can actually reach, not what was typed.
        "file_roots": [str(root) for root in roots()],
        # The catalogue the model is given. Named here so an operator can see
        # exactly what their assistant has been handed, without reading the code.
        "tools": [
            {"name": tool.name, "level": tool.level.name.lower()}
            for tool in dispatcher.catalogue()
        ],
        # Stated, not implied: writing and running commands always stop for a
        # person, even once they are switched on.
        "approval_required_for": ["write", "shell"],
    }
