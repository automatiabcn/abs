# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The two tools that can change something, and therefore never run alone.

Everything here is L2 or L3, which means the dispatcher will not execute any of
it on the model's say-so: the call is turned into an approval a person has to
read and accept, and only then does the function below actually run. That is the
whole design — these are not "dangerous tools with a warning", they are tools
that structurally cannot fire without a human, and the tests prove it by pointing
a prompt injection straight at them.

Two things still matter even behind a human:

**A person approving a write should be approving a *place*.** The write path is
the same boundary as the read path (paths.py) — inside the operator's roots,
never a secret file — because "I approved a note in my documents folder" must not
be a way to land bytes in ~/.ssh.

**A person approving a command should be approving what they read.** The shell
runs the exact string shown in the approval, with a timeout, without a login
shell's dotfiles, and with the server's own provider keys stripped from the
environment — so an innocuous-looking pipeline cannot quietly print the API keys
of the machine it is running on to a transcript that gets stored and indexed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.agentic.paths import MAX_FILE_BYTES, PathDenied, resolve, roots
from app.config import settings

logger = logging.getLogger(__name__)

# A command that has not finished by now is not going to, and nobody is waiting
# at a chat window for it.
SHELL_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_CHARS = 4000

# Names the server's own credentials live under. A shell command inherits the
# server's environment, and the server's environment is where the vault key is.
_SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "DSN", "DATABASE_URL")


async def fs_write(path: str, content: str) -> str:
    """Write a text file inside an allowed root. Only ever called post-approval."""
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise PathDenied(
            f"that content is larger than {MAX_FILE_BYTES // 1000} KB — too big to write from a chat"
        )

    # must_exist=False: writing a *new* file is the common case, and the
    # boundary check does not need the file to be there — it needs the
    # destination to be inside a root and not a secret.
    target = resolve(path, must_exist=False)
    if target.is_dir():
        raise PathDenied(f"{target} is a folder, not a file")

    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    logger.info("agent fs_write %s (%s)", target, "overwrote" if existed else "created")
    verb = "Overwrote" if existed else "Created"
    return f"{verb} {target} ({len(content)} characters)."


def _clean_env() -> dict[str, str]:
    """The server's environment, minus the server's secrets."""
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in _SECRET_ENV_MARKERS)
    }


def _working_dir() -> Path:
    allowed = roots()
    if allowed:
        return allowed[0]
    return Path(settings.agent_shell_cwd or ".").expanduser().resolve()


async def run_command(command: str) -> str:
    """Run a shell command. Only ever called post-approval, on the exact string a
    person read and accepted."""
    if not command.strip():
        raise PathDenied("no command given")

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(_working_dir()),
        env=_clean_env(),
    )
    try:
        raw, _ = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise PathDenied(
            f"the command was still running after {int(SHELL_TIMEOUT_SECONDS)} seconds and was stopped"
        ) from None

    output = raw.decode("utf-8", errors="replace").strip()
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n… [output truncated]"

    # A non-zero exit is a fact about the command, not a failure of the tool: the
    # model needs to see it to reason about what to do next.
    status = "finished" if proc.returncode == 0 else f"exited with code {proc.returncode}"
    return f"$ {command}\n[{status}]\n{output or '(no output)'}"
