# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Read-only inventory of test/QA fixtures left in a customer instance.

Outputs JSON to stdout and (by default) a markdown summary to
``artifacts/test_data_audit.md``. NEVER deletes anything — this is the
preflight step that runs before ``reset_test_data.py --confirm``.

Usage::

    python scripts/audit_test_data.py
    python scripts/audit_test_data.py --no-md       # JSON only
    python scripts/audit_test_data.py --out PATH    # custom md path

Categories: users, chats, workflows, rag, audits, licenses, beta_requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _test_data_lib import run  # noqa: E402


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Test data audit\n")
    lines.append(f"- mode: `{report['mode']}`")
    lines.append(f"- started_at: `{report['started_at']}`")
    lines.append(f"- duration_s: `{report['duration_s']}`")
    lines.append(f"- total_matched: **{report['total_matched']}**")
    lines.append(
        f"- protected_emails: {', '.join('`' + e + '`' for e in report['protected_emails'])}"
    )
    lines.append(
        f"- protected_tenants: {', '.join('`' + t + '`' for t in report['protected_tenants'])}"
    )
    lines.append("")
    lines.append("| category | matched | sample |")
    lines.append("| --- | --- | --- |")
    for cat, payload in report["categories"].items():
        sample = ", ".join(
            sorted({s.get("email") or s.get("user_email") or s.get("file") or s.get("id") or "—" for s in payload["samples"][:3]})
        ) or "—"
        lines.append(f"| {cat} | {payload['matched']} | {sample} |")
    lines.append("")
    lines.append("## Sample rows\n")
    for cat, payload in report["categories"].items():
        if not payload["samples"]:
            continue
        lines.append(f"### {cat}\n")
        lines.append("```json")
        lines.append(json.dumps(payload["samples"], indent=2, default=str))
        lines.append("```\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        default=str(REPO_ROOT / "artifacts" / "test_data_audit.md"),
        help="Markdown output path (default: artifacts/test_data_audit.md)",
    )
    p.add_argument("--no-md", action="store_true", help="Skip markdown file")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    report = run(confirm=False, purge_rag=False)
    print(json.dumps(report, indent=2, default=str))

    if not args.no_md:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_markdown(report), encoding="utf-8")
        if not args.quiet:
            print(f"\n[audit] markdown → {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
