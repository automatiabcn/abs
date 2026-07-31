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

import os
import platform
import shutil
from dataclasses import dataclass

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


def status() -> MicroVMStatus:
    """What Tier-2 would need here, and what is actually present."""
    system = platform.system()
    helper = shutil.which(_HELPER_NAME) or ""

    if system == "Darwin":
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

    # A helper on PATH is still only a claim — the tier stays unavailable
    # until a self-test proves a command runs inside the VM. That test ships
    # with the helper; its absence here is deliberate fail-closed.
    return MicroVMStatus(
        TIER, False, True,
        f"{_HELPER_NAME} found but unproven — self-test not implemented yet",
    )
