# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Hardware fingerprint collection for license binding (Q12 IP-Hardening R1).

A SHA-256 hash of four OS-level identifiers — stable across reboots but
unique to a given machine. License JWTs that embed `machine_fp` are only
honoured on the host whose live fingerprint matches.

Components (joined with '|', then hashed):
    1. /etc/machine-id (Linux) / IOPlatformUUID (macOS) — most stable
    2. First non-loopback MAC address (uuid.getnode() fallback)
    3. CPU model string (platform.processor())
    4. Hostname (low-entropy variance)
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from pathlib import Path


def _machine_id() -> str | None:
    machine_id = Path("/etc/machine-id")
    if machine_id.exists():
        try:
            return machine_id.read_text().strip() or None
        except OSError:
            return None
    if platform.system() == "Darwin":
        try:
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode()
        except (subprocess.SubprocessError, OSError):
            return None
        for line in out.splitlines():
            if "IOPlatformUUID" in line:
                pieces = line.split('"')
                if len(pieces) >= 4:
                    return pieces[3]
    return None


def _mac_address() -> str | None:
    try:
        import uuid

        node = uuid.getnode()
    except Exception:
        return None
    return format(node, "x") if node else None


def collect_machine_fingerprint() -> str:
    """Return a stable SHA-256 fingerprint of the host machine.

    Raises:
        RuntimeError: if no fingerprint components could be collected at
            all (extremely degraded environment — refuse to mint a fake
            FP that would silently match).
    """

    parts: list[str] = []

    mid = _machine_id()
    if mid:
        parts.append(mid)

    mac = _mac_address()
    if mac:
        parts.append(mac)

    cpu = platform.processor() or platform.machine()
    if cpu:
        parts.append(cpu)

    host = platform.node()
    if host:
        parts.append(host)

    if not parts:
        raise RuntimeError("could not collect any fingerprint components")

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _main(argv: list[str] | None = None) -> int:
    """CLI helper: ``python -m app.licensing.fingerprint --print``.

    Customer runs this on their server and copy-pastes the hex digest
    to the vendor during onboarding so the license can be minted with
    matching ``machine_fp``.
    """

    args = argv if argv is not None else sys.argv[1:]
    if "--print" in args or not args:
        print(collect_machine_fingerprint())
        return 0
    print("usage: python -m app.licensing.fingerprint --print", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
