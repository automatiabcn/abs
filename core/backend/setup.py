# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Optional Cython compile of license-critical modules (IP hardening).

Source-readable Python lets a reverse engineer flip ``verify_license``
to ``return {"valid": True}`` in a few seconds. Compiling these modules
to ``.so`` shared libraries forces them through a disassembler — order
of magnitude harder.

Used **only** in production image builds:

    pip install cython
    python setup.py build_ext --inplace

Dev environments keep importing the regular ``.py`` files. The compiled
modules are import-compatible with the source ones, so pytest passes
either way.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Modules to compile. Add new ones cautiously — every entry here becomes
# harder to debug for ops because tracebacks no longer show line numbers
# from the source.
LICENSE_CRITICAL_MODULES = [
    "app/licensing/verifier.py",
    "app/licensing/fingerprint.py",
    "app/observability/quota_monitor.py",
]


def _build_kwargs() -> dict[str, Any]:
    """Cython compile is gated behind setuptools' build_ext. When this
    module is imported as part of `pip install .` (no build_ext call),
    we return a lightweight package definition so the wheel still works
    without Cython on the path.
    """

    base: dict[str, Any] = {
        "name": "abs-backend-compiled",
        "version": "0.1.0",
        "packages": ["app"],
    }

    if os.environ.get("ABS_COMPILE_CYTHON") != "1":
        return base

    try:
        from Cython.Build import cythonize  # type: ignore[import-not-found]
    except ImportError:
        print(
            "[setup.py] ABS_COMPILE_CYTHON=1 but Cython is not installed.",
            file=sys.stderr,
        )
        sys.exit(2)

    backend_root = Path(__file__).resolve().parent
    targets = []
    for rel in LICENSE_CRITICAL_MODULES:
        path = backend_root / rel
        if not path.exists():
            print(f"[setup.py] WARN: target missing, skipping {rel}", file=sys.stderr)
            continue
        targets.append(str(path))

    base["ext_modules"] = cythonize(targets, language_level=3)
    return base


if __name__ == "__main__":
    from setuptools import setup

    setup(**_build_kwargs())
