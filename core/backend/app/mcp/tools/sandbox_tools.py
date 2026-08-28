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
from app.sandbox.verdict import environment_failure

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
    from app.sandbox import microvm

    mechanism = _sandbox.available_mechanism()
    net_blocked = _sandbox.network_is_blocked(mechanism)
    mvm = microvm.status()
    if not mechanism:
        note = "No OS sandbox here, so ABS will not run commands at all."
    elif net_blocked:
        note = (
            "Commands may write only inside the workspace and cannot reach the network; reads are broad (a toolchain needs them) except credential stores and the server's own state. "
            "This contains an agent that goes wrong; it does not contain "
            "code written to be hostile — that needs the opt-in microVM."
        )
    else:
        # restricted-token: writes are confined, the network is not — say it
        # here, where the Run button decides what to print.
        note = (
            "Commands run write-confined to the workspace; the network is "
            "NOT blocked by this tier. Hostile code still needs the microVM."
        )
    return json.dumps(
        {
            "ok": True,
            "mechanism": mechanism,
            "can_run": bool(mechanism),
            "tier": "os-native" if mechanism else "",
            "network_blocked": net_blocked,
            "installs_required": [],
            "tiers": [
                {
                    "tier": "os-native",
                    "mechanism": mechanism,
                    "available": bool(mechanism),
                    "network_blocked": net_blocked,
                },
                {
                    "tier": mvm.tier,
                    "available": mvm.available,
                    "platform_capable": mvm.platform_capable,
                    "reason": mvm.reason,
                },
            ],
            "note": note,
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
    """Run a check (tests, lint, build): writes confined to the workspace,
    network off, credential stores and server state unreadable.

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

    # Where the check may run is the same rule as where a project may be. The
    # sandbox confines WRITES to the workspace; reads are broad because a
    # toolchain needs them — so a workspace_root pointing at the server's own
    # state directory read `.env` straight into stdout (audit, 2026-08-18).
    from app.workspace.current import problem_with_root

    try:
        from app.mcp.context import get_mcp_caller

        _tenant, _user = get_mcp_caller()
    except Exception:  # noqa: BLE001
        _tenant = ""
    bad = problem_with_root(workspace_root, str(_tenant or ""))
    if bad:
        return json.dumps({"ok": False, "refused": bad}, ensure_ascii=False)

    # Off the event loop: a two-minute test suite must not freeze Tab, the
    # title bar and every other client of this server while it runs. And a
    # caller cannot ask for an hour.
    import asyncio as _asyncio

    res = await _asyncio.to_thread(
        _sandbox.run,
        argv,
        workspace_root=workspace_root,
        allow_network=allow_network,
        timeout=min(max(float(timeout), 1.0), 600.0),
    )
    # A check that never reached the code is not a verdict on the code: a
    # missing module at collection, a runner that is not installed, a stub
    # interpreter. Named here so the panel can say "unverified — why" instead
    # of FAILED + "Undo this change" (live, 08-28, G8).
    environment = environment_failure(res.exit_code, res.stdout, res.stderr)
    return json.dumps(
        {
            "ok": res.ok,
            # Exit 0 with nothing said proves nothing: a ten-byte stub where
            # the interpreter should be exits 0 in silence, and "passed" over
            # it would be the kind of green that costs a customer (live,
            # 08-28: an evicted .venv/bin/python). The panel treats this as
            # "unverified", never as a pass.
            "inconclusive": bool(
                environment is not None
                or (res.ok and not (res.stdout or "").strip() and not (res.stderr or "").strip())
            ),
            "environment": environment,
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "mechanism": res.mechanism,
            "duration_ms": res.duration_ms,
            "refused": res.refused,
            "truncated": res.truncated,
            # What the TIER can promise, not what the flag asked for: a
            # Windows restricted token never blocks the network, and printing
            # "blocked" over it would be a lie the user acts on.
            "network": (
                "allowed"
                if allow_network
                else (
                    "blocked"
                    if _sandbox.network_is_blocked(res.mechanism or "")
                    else "not blocked by this tier"
                )
            ),
        },
        ensure_ascii=False,
    )


REGISTERED_TOOLS.extend(["sandbox_status", "sandbox_run"])
