# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Boot-time integrity check for the verifier module (IP hardening).

A reverse engineer's first move is editing ``verifier.py`` to make
``verify_license`` return a constant payload. We hash the live module
file at boot and compare to a hash baked into the image at build time.
Mismatch => panic. With R5 (Cython), the file becomes a ``.so`` whose
hash is trivially stable across releases of the same version.

The expected hash is resolved in this order:

1. ``/etc/abs.verifier.hash`` — written by the Dockerfile builder stage
   from the ``.so`` actually shipped (production image gate).
2. ``ABS_VERIFIER_HASH`` env var — backwards compatibility / dev escape.
3. Empty — gate is a no-op (dev environments without a baked hash).

A pilot found this gate silently
disabled in production: ``_verifier_path()`` returned ``verifier.py``
which the Dockerfile strips, and ``ABS_VERIFIER_HASH`` was never set.
Both are now fixed: path resolves the ``.so`` and the gate reads the
hash from the build-time file.

Disable in tests with ``ABS_TAMPER_CHECK_DISABLED=1``.
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Production gate file written by the Dockerfile builder stage.
_HASH_FILE = Path("/etc/abs.verifier.hash")


def _verifier_path() -> Path:
    """Resolve the verifier module on disk regardless of cwd.

    Production images ship the Cython-compiled
    ``verifier.cpython-<abi>-<arch>.so``; dev environments keep the
    ``.py`` source. Prefer the ``.so`` so the gate is exercised in prod.
    """

    parent = Path(__file__).resolve().parent
    so_files = sorted(glob.glob(str(parent / "verifier*.so")))
    if so_files:
        return Path(so_files[0])
    return parent / "verifier.py"


def _expected_hash() -> str:
    """Resolve the expected verifier hash.

    Prefers ``/etc/abs.verifier.hash`` (production, written at image
    build time). Falls back to ``ABS_VERIFIER_HASH`` env so dev/test
    can opt in without touching the filesystem.
    """

    if _HASH_FILE.exists():
        try:
            value = _HASH_FILE.read_text().strip()
            if value:
                return value
        except OSError as exc:
            logger.warning("tamper_check_hash_file_unreadable: %s", exc)
    return os.environ.get("ABS_VERIFIER_HASH", "").strip()


def compute_verifier_hash(path: Path | None = None) -> str:
    """SHA-256 of the verifier module bytes (whatever extension)."""

    target = path or _verifier_path()
    return hashlib.sha256(target.read_bytes()).hexdigest()


def verify_self_integrity() -> bool:
    """Return True iff the live verifier hash matches the build-time expectation.

    This used to return True when no expected hash could be found — so the licence
    verifier's tamper check was defeated by *deleting the hash*, which is strictly
    easier than patching the verifier the hash protects. A guard that passes when
    the thing it needs is missing is not a guard.

    Development is already served by an explicit `ABS_TAMPER_CHECK_DISABLED=1`
    (see `assert_self_integrity`), so it never needed this second, silent escape —
    and unlike the flag, the silent one also worked in production.
    """

    expected = _expected_hash()
    if not expected:
        target = _verifier_path()
        if target.suffix == ".so":
            # A compiled verifier means this is a production image, and a production
            # image is built with its hash. The hash being absent *here* is not a
            # dev convenience — it is the state an attacker creates, because
            # deleting the hash file is far easier than patching the .so it
            # protects. Refuse.
            logger.critical(
                "tamper_check_no_expected_hash path=%s — the verifier is compiled "
                "but its build-time hash is missing; refusing to trust it",
                target,
            )
            return False
        # Source checkout: the verifier is a .py sitting right there, no hash is
        # built, and there is nothing to protect that the reader cannot already
        # edit. Passing is honest. (`ABS_TAMPER_CHECK_DISABLED=1` remains the way
        # to skip the check deliberately.)
        return True
    try:
        actual = compute_verifier_hash()
    except OSError as exc:
        logger.critical(
            "tamper_check_read_failed path=%s err=%s", _verifier_path(), exc
        )
        return False
    if actual != expected:
        logger.critical(
            "tamper_check_FAIL expected=%s actual=%s path=%s",
            expected[:12],
            actual[:12],
            _verifier_path(),
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
