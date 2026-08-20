# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tier-2 isolation: a microVM. Detection only, honestly.

Tier-1 (seatbelt / bubblewrap / restricted-token) contains an agent that
goes wrong; it does not contain code WRITTEN to be hostile — an `npm
install` from a stranger's lockfile belongs behind a hardware boundary.
On macOS that boundary is Virtualization.framework (no special Apple
entitlement needed beyond `com.apple.security.virtualization`); on Linux
it is KVM.

What ships today is the truth about this machine: whether the platform
COULD run the tier, and that our helper (a small VM host binary plus a
guest image with an exec agent) is not built yet. `available()` is False
until a helper exists AND proves itself, the same self-test discipline the
Windows token follows. A tier that reports ready before it can run one
command would be the exact dishonesty the sandbox exists to prevent.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TIER = "microvm"

# The helper this module will drive once it exists. Kept in one place so the
# day it ships, detection and refusal messages stay in step.
_HELPER_NAME = "abs-vmhost"


@dataclass
class MicroVMStatus:
    tier: str
    available: bool
    platform_capable: bool
    reason: str
    # What the helper measured, when there is a helper to ask. None means the
    # capability was inferred from the platform rather than observed.
    measured: dict | None = None


def _ask_helper(helper: str) -> dict | None:
    """Ask abs-vmhost whether THIS machine can host a microVM.

    The helper builds a real VZ configuration and validates it, so the answer
    comes from Virtualization.framework rather than from us. Any failure to
    ask is None — an unanswered question, never a yes.
    """
    try:
        proc = subprocess.run(
            [helper, "--probe"], capture_output=True, text=True, timeout=15
        )
        line = (proc.stdout or "").strip().splitlines()
        return json.loads(line[-1]) if line else None
    except Exception as exc:  # noqa: BLE001 — a probe that cannot run says nothing
        logger.debug("vmhost probe failed: %s", exc)
        return None


def status() -> MicroVMStatus:
    """What Tier-2 would need here, and what is actually present."""
    system = platform.system()
    helper = shutil.which(_HELPER_NAME) or ""

    if system == "Darwin":
        # The framework ships with macOS, so its presence proves nothing about
        # this process: without the com.apple.security.virtualization
        # entitlement the framework refuses every configuration (measured
        # 08-01). Only the helper can tell the difference, so "capable" here
        # means "worth asking the helper", not "able".
        capable = os.path.exists(
            "/System/Library/Frameworks/Virtualization.framework"
        )
        if not capable:
            return MicroVMStatus(TIER, False, False,
                                 "Virtualization.framework not present")
        if not helper:
            return MicroVMStatus(
                TIER, False, True,
                f"platform ready ({_HELPER_NAME} helper + guest image not built yet)",
            )
    elif system == "Linux":
        capable = os.path.exists("/dev/kvm")
        if not capable:
            return MicroVMStatus(TIER, False, False, "/dev/kvm not present")
        if not helper:
            return MicroVMStatus(
                TIER, False, True,
                f"KVM ready ({_HELPER_NAME} helper + guest image not built yet)",
            )
    else:
        return MicroVMStatus(TIER, False, False,
                             f"no microVM path planned for {system} yet")

    # A helper on PATH is a claim; its probe is a measurement. Even a probe
    # that says "yes" leaves the tier unavailable until a command has actually
    # RUN inside a VM — the framework accepting a configuration is not the
    # same as a guest that executes anything.
    probe = _ask_helper(helper)
    if probe is None:
        return MicroVMStatus(
            TIER, False, True,
            f"{_HELPER_NAME} is on PATH but did not answer its probe",
        )
    if not probe.get("ok"):
        return MicroVMStatus(
            TIER, False, True,
            str(probe.get("reason") or "the helper reported it cannot host a VM"),
            measured=probe,
        )
    return MicroVMStatus(
        TIER, False, True,
        "the helper can host a VM; no command has been run inside one yet",
        measured=probe,
    )
