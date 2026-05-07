# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Boot-time integrity check for the verifier source (Q12 IP-Hardening R4).

A reverse engineer's first move is editing ``verifier.py`` to make
``verify_license`` return a constant payload. We hash the file at boot
and compare to a hash baked into the image at build time. Mismatch =>
panic. With R5 (Cython), the file becomes a ``.so`` whose hash is
trivially stable across releases of the same version.

Disable in tests with ``ABS_TAMPER_CHECK_DISABLED=1``.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _verifier_path() -> Path:
    """Resolve the verifier module on disk regardless of cwd."""

    return Path(__file__).resolve().parent / "verifier.py"


def compute_verifier_hash(path: Path | None = None) -> str:
    """SHA-256 of the verifier source bytes (whatever extension)."""

    target = path or _verifier_path()
    return hashlib.sha256(target.read_bytes()).hexdigest()


def verify_self_integrity() -> bool:
    """Return True iff the live verifier hash matches the build-time
    expectation. Returns True (no-op) when the expected hash is unset
    so dev environments are not blocked by a missing build arg.
    """

    expected = os.environ.get("ABS_VERIFIER_HASH", "").strip()
    if not expected:
        return True
    try:
        actual = compute_verifier_hash()
    except OSError as exc:
        logger.warning("tamper_check_read_failed: %s", exc)
        return False
    if actual != expected:
        logger.critical(
            "tamper_check_FAIL expected=%s actual=%s",
            expected[:12],
            actual[:12],
        )
        return False
    return True


def assert_self_integrity() -> None:
    """Raise ``RuntimeError`` if the verifier source has been tampered with.

    Honours ``ABS_TAMPER_CHECK_DISABLED=1`` for development.
    """

    if os.environ.get("ABS_TAMPER_CHECK_DISABLED") == "1":
        return
    if not verify_self_integrity():
        raise RuntimeError("license_verifier_tampered")
