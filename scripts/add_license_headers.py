#!/usr/bin/env python3
"""Add BSL 1.1 copyright header to all source files.

Idempotent — files already containing "Copyright (c) 2026 Automatia"
are skipped. Run once after switching LICENSE to BSL.

Usage:
    python scripts/add_license_headers.py            # apply
    python scripts/add_license_headers.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PY_HEADER = """\
# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""

TS_HEADER = """\
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

"""

EXISTING_MARKER = "Copyright (c) 2026 Automatia"

PY_GLOB = [
    "core/backend/app/**/*.py",
    "scripts/**/*.py",
]
TS_GLOB = [
    "core/landing/app/**/*.ts",
    "core/landing/app/**/*.tsx",
    "core/landing/components/**/*.ts",
    "core/landing/components/**/*.tsx",
    "core/landing/lib/**/*.ts",
]

EXCLUDE_PARTS = {"__pycache__", "node_modules", ".next", "dist", ".venv", "venv"}


def is_excluded(p: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in p.parts)


def collect_files() -> tuple[list[Path], list[Path]]:
    py: list[Path] = []
    for pattern in PY_GLOB:
        for f in ROOT.glob(pattern):
            if f.is_file() and not is_excluded(f.relative_to(ROOT)):
                py.append(f)
    ts: list[Path] = []
    for pattern in TS_GLOB:
        for f in ROOT.glob(pattern):
            if f.is_file() and not is_excluded(f.relative_to(ROOT)):
                ts.append(f)
    return py, ts


def has_header(content: str) -> bool:
    return EXISTING_MARKER in content[:500]


def add_py_header(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    if has_header(text):
        return False
    # Preserve shebang if present
    lines = text.split("\n", 1)
    if lines[0].startswith("#!"):
        new = lines[0] + "\n" + PY_HEADER + (lines[1] if len(lines) > 1 else "")
    else:
        new = PY_HEADER + text
    if not dry_run:
        path.write_text(new, encoding="utf-8")
    return True


def add_ts_header(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    if has_header(text):
        return False
    # If file starts with "use client" / "use server" directive, place
    # header AFTER the directive line for Next.js correctness.
    if text.startswith('"use client"') or text.startswith("'use client'") \
            or text.startswith('"use server"') or text.startswith("'use server'"):
        lines = text.split("\n", 1)
        new = lines[0] + "\n" + TS_HEADER + (lines[1] if len(lines) > 1 else "")
    else:
        new = TS_HEADER + text
    if not dry_run:
        path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    py_files, ts_files = collect_files()
    py_added = sum(add_py_header(f, args.dry_run) for f in py_files)
    ts_added = sum(add_ts_header(f, args.dry_run) for f in ts_files)

    mode = "(dry-run)" if args.dry_run else "(applied)"
    print(f"Python files scanned: {len(py_files)}, headers added: {py_added} {mode}")
    print(f"TS/TSX files scanned: {len(ts_files)}, headers added: {ts_added} {mode}")
    print(f"Total: {py_added + ts_added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
