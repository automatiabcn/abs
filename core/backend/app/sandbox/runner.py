# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Run a command with the isolation the operating system already provides.

Tier 1 of the sandbox plan: **nothing to install**. macOS has Seatbelt, Linux
has Landlock/bubblewrap, Windows has restricted tokens — every one of them
ships with the OS. Requiring Docker instead would cost the user 6 GB of disk,
~4 GB of idle RAM, a licence above 250 employees, and — because Docker's
air-gapped feature is a Business subscription — would put a per-seat bill on
the very tier that exists to avoid vendor dependencies.

Two rules decide everything here:

- **Fail closed.** If isolation cannot be established, the command does NOT
  run. The alternative was measured in the field: an agent that could not get
  past its own denylist turned the sandbox off and carried on.
- **Say which isolation was used.** A caller that believes it ran sandboxed
  when it did not is worse off than one that knows it has none. Every result
  carries the mechanism by name.

Honest about the threat model: this tier contains an agent that goes *wrong*.
It does not contain code written to be *hostile* (a malicious postinstall
script, a kernel LPE). That is what the opt-in microVM tier is for, and the
caller is told which one it is getting.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120.0
_MAX_OUTPUT = 40_000


@dataclass
class SandboxResult:
    ok: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    # Which isolation actually ran this — never a guess, never a default.
    mechanism: str = ""
    duration_ms: int = 0
    refused: str = ""
    truncated: bool = False
    env_allowed: List[str] = field(default_factory=list)


def available_mechanism() -> str:
    """The strongest Tier-1 isolation this machine can give us, or ''."""
    system = platform.system()
    if system == "Darwin":
        return "seatbelt" if os.path.exists("/usr/bin/sandbox-exec") else ""
    if system == "Linux":
        # bubblewrap is the practical wrapper; Landlock alone needs a helper
        # binary we do not ship yet.
        return "bubblewrap" if shutil.which("bwrap") else ""
    if system == "Windows":
        # Only after the machine PROVES the containment (spawn under the
        # token, write inside the grant, fail to write outside it). An
        # unproven mechanism reporting available is how "sandboxed" becomes
        # a label instead of a property.
        from app.sandbox import windows_token

        return windows_token.MECHANISM if windows_token.self_test() else ""
    return ""


def network_is_blocked(mechanism: str) -> bool:
    """Whether this mechanism actually cuts the network off.

    seatbelt and bubblewrap deny the network in their profiles; a Windows
    restricted token does not touch it. Callers print the network state to
    users — they must print what the tier can promise, not what the flag
    asked for.
    """
    return mechanism in ("seatbelt", "bubblewrap")


def _seatbelt_profile(workspace: str, allow_network: bool) -> str:
    """Deny by default; open only the workspace for writing.

    Inverted defaults are how the 2026 sandbox escapes happened — an allow-all
    profile with holes patched in cannot be made safe, so this starts closed.
    Reads stay broad because a build needs its toolchain, headers and caches;
    the boundary that matters for an agent is what it can WRITE and where it
    can talk to.
    """
    ws = os.path.realpath(workspace).replace('"', '\\"')
    tmp = tempfile.gettempdir().replace('"', '\\"')
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec process-fork)",
        "(allow sysctl-read)",
        "(allow file-read*)",
        "(allow mach-lookup)",
        "(allow signal (target same-sandbox))",
        f'(allow file-write* (subpath "{ws}"))',
        f'(allow file-write* (subpath "{tmp}"))',
        "(allow file-write-data (literal \"/dev/null\") (literal \"/dev/stdout\")"
        " (literal \"/dev/stderr\"))",
    ]
    if allow_network:
        lines.append("(allow network*)")
    return "\n".join(lines) + "\n"


def _bwrap_argv(workspace: str, allow_network: bool) -> List[str]:
    ws = os.path.realpath(workspace)
    argv = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--bind", ws, ws,
        "--bind", tempfile.gettempdir(), tempfile.gettempdir(),
        "--proc", "/proc",
        "--dev", "/dev",
        "--die-with-parent",
        "--new-session",
    ]
    if not allow_network:
        argv.append("--unshare-net")
    return argv


# The variables a build genuinely needs. Everything else — tokens, cloud
# credentials, provider keys — stays out: an agent that never sees a secret
# cannot leak one, and this is cheaper than auditing what it did with it.
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TERM", "TMPDIR")


def _clean_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def run(
    command: List[str],
    *,
    workspace_root: str,
    allow_network: bool = False,
    timeout: float = _DEFAULT_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
) -> SandboxResult:
    """Run ``command`` confined to ``workspace_root``.

    Network is off unless asked for: a build that suddenly wants the network is
    exactly the moment worth interrupting a developer over.
    """
    import time

    if not command:
        return SandboxResult(False, None, "", "", refused="no command given")
    ws = os.path.realpath(workspace_root or "")
    if not ws or not os.path.isdir(ws):
        return SandboxResult(
            False, None, "", "", refused=f"workspace not found: {workspace_root}"
        )

    mechanism = available_mechanism()
    if not mechanism:
        # Fail closed. Running unconfined here would make every caller's
        # "sandboxed" label a lie.
        return SandboxResult(
            False,
            None,
            "",
            "",
            refused=(
                f"no OS sandbox available on {platform.system()} — refusing to "
                "run unconfined"
            ),
        )

    if mechanism == "restricted-token":
        # Windows: token-confined writes; the network is NOT blocked by this
        # tier and the result says so via network_is_blocked().
        from app.sandbox import windows_token

        started = time.monotonic()
        try:
            code, out, err = windows_token.run(
                command, workspace_root=ws, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                False, None, "", "",
                mechanism=mechanism,
                duration_ms=int((time.monotonic() - started) * 1000),
                refused=f"timed out after {timeout:.0f}s",
            )
        except Exception as exc:  # noqa: BLE001 — refusal beats unconfined
            return SandboxResult(
                False, None, "", "",
                mechanism=mechanism,
                refused=f"restricted-token run failed: {exc}",
            )
        truncated = len(out) > _MAX_OUTPUT or len(err) > _MAX_OUTPUT
        return SandboxResult(
            ok=code == 0,
            exit_code=code,
            stdout=out[:_MAX_OUTPUT],
            stderr=err[:_MAX_OUTPUT],
            mechanism=mechanism,
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=truncated,
        )

    profile_path = ""
    if mechanism == "seatbelt":
        fd, profile_path = tempfile.mkstemp(suffix=".sb")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_seatbelt_profile(ws, allow_network))
        argv = ["/usr/bin/sandbox-exec", "-f", profile_path, *command]
    else:
        argv = [*_bwrap_argv(ws, allow_network), *command]

    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=ws,
            env=_clean_env(env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out, err, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return SandboxResult(
            False, None, "", "",
            mechanism=mechanism,
            duration_ms=int((time.monotonic() - started) * 1000),
            refused=f"timed out after {timeout:.0f}s",
        )
    except OSError as exc:
        return SandboxResult(
            False, None, "", "", mechanism=mechanism, refused=f"could not start: {exc}"
        )
    finally:
        if profile_path:
            try:
                os.unlink(profile_path)
            except OSError:
                pass

    truncated = len(out) > _MAX_OUTPUT or len(err) > _MAX_OUTPUT
    return SandboxResult(
        ok=code == 0,
        exit_code=code,
        stdout=out[:_MAX_OUTPUT],
        stderr=err[:_MAX_OUTPUT],
        mechanism=mechanism,
        duration_ms=int((time.monotonic() - started) * 1000),
        truncated=truncated,
        env_allowed=sorted(_clean_env(env).keys()),
    )
