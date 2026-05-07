# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Idempotent purge of test/QA fixtures before customer delivery.

By default runs in ``--dry-run`` mode and prints a JSON report identical
in shape to ``audit_test_data.py``. Pass ``--confirm`` to actually delete.
``--purge-rag`` extends the deletion to fixture chunks in the Chroma
collection.

Protected (never touched):
  * Bootstrap admin email (``admin@demo-acme.com``) and any address in
    PROTECTED_EMAILS.
  * Paid licence rows where ``tier`` ∈ {self-host, team, enterprise}.
  * Real customer tenants (``demo-acme``, ``default``) — the helpers
    only delete by per-row email pattern, never by tenant alone.

A second ``--confirm`` invocation right after the first should report
``total_deleted == 0`` (idempotent).

Usage::

    python scripts/reset_test_data.py                  # dry-run
    python scripts/reset_test_data.py --confirm
    python scripts/reset_test_data.py --confirm --purge-rag
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _test_data_lib import run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete (default: dry-run preview only).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run (default behaviour without --confirm).",
    )
    p.add_argument(
        "--purge-rag",
        action="store_true",
        help="Also delete fixture chunks from the Chroma collection.",
    )
    args = p.parse_args(argv)

    if args.confirm and args.dry_run:
        print("--confirm and --dry-run are mutually exclusive", file=sys.stderr)
        return 2

    report = run(confirm=args.confirm, purge_rag=args.purge_rag)
    print(json.dumps(report, indent=2, default=str))

    if args.confirm:
        print(
            f"\n[reset] mode=confirm deleted={report['total_deleted']} "
            f"purge_rag={args.purge_rag}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
