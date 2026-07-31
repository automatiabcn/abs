# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sandbox MCP tools — let the agent actually run something, safely.

This is the half the product was missing: it could propose a change and grade
it, but never find out whether the tests still pass. Running goes through the
OS sandbox (Tier 1, nothing to install) and fails closed — a caller that asks
for a command on a machine with no isolation gets a refusal, not an
unconfined process.

`sandbox_status` exists so a surface can tell the user what protection it has
BEFORE offering to run anything. A panel that offers a Run button on a machine
where running is refused is a promise the product cannot keep.
"""

from __future__ import annotations

import json
import shlex
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.sandbox import runner as _sandbox

REGISTERED_TOOLS: List[str] = []

# Only commands a developer would recognise as "check my work". Anything that
# installs, publishes or deploys is deliberately absent: an allowlist of whole
# commands is the control, not a denylist of arguments — the escapes of 2026
# were written by people who knew every denylist entry.
_ALLOWED_PROGRAMS = frozenset(
    {
        "pytest", "python", "python3", "node", "npm", "npx", "yarn", "pnpm",
        "go", "cargo", "make", "ruff", "eslint", "tsc", "jest", "vitest",
        "mvn", "gradle", "dotnet", "swift", "rspec", "bundle", "phpunit",
    }
)


@mcp_server.tool()
@with_hooks("sandbox_status")
async def sandbox_status() -> str:
    """What isolation this machine can give a command, before one is offered.

    `mechanism` is empty when the OS gives us nothing we trust — in that case
    running is refused rather than done unconfined, and a surface should say so
    instead of showing a Run button.
    """
    await tracker.bump("sandbox_status")
    mechanism = _sandbox.available_mechanism()
    return json.dumps(
        {
            "ok": True,
            "mechanism": mechanism,
            "can_run": bool(mechanism),
            "tier": "os-native" if mechanism else "",
            "installs_required": [],
            "note": (
                "Commands run confined to the workspace with the network off. "
                "This contains an agent that goes wrong; it does not contain "
                "code written to be hostile — that needs the opt-in microVM."
                if mechanism
                else "No OS sandbox here, so ABS will not run commands at all."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("sandbox_run")
async def sandbox_run(
    command: str,
    workspace_root: str,
    allow_network: bool = False,
    timeout: float = 120.0,
) -> str:
    """Run a check (tests, lint, build) confined to the workspace.

    The program must be one ABS recognises as a check — installing, publishing
    and deploying are not on that list, so the agent cannot reach for them.
    Network is off unless explicitly asked for.
    """
    await tracker.bump("sandbox_run")
    try:
        argv = shlex.split(command or "")
    except ValueError as exc:
        return json.dumps({"ok": False, "refused": f"unparseable command: {exc}"})
    if not argv:
        return json.dumps({"ok": False, "refused": "no command given"})

    program = argv[0].rsplit("/", 1)[-1]
    if program not in _ALLOWED_PROGRAMS:
        return json.dumps(
            {
                "ok": False,
                "refused": (
                    f"{program} is not one of the checks ABS may run. "
                    f"Allowed: {', '.join(sorted(_ALLOWED_PROGRAMS))}"
                ),
            },
            ensure_ascii=False,
        )

    res = _sandbox.run(
        argv,
        workspace_root=workspace_root,
        allow_network=allow_network,
        timeout=float(timeout),
    )
    return json.dumps(
        {
            "ok": res.ok,
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "mechanism": res.mechanism,
            "duration_ms": res.duration_ms,
            "refused": res.refused,
            "truncated": res.truncated,
            "network": "allowed" if allow_network else "blocked",
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.extend(["sandbox_status", "sandbox_run"])
