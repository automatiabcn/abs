# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""G4 — Seed the `demo-acme` tenant for the customer-journey playthrough.

Idempotent: running it twice produces the same on-disk fixture and the same
audit-log line. Designed to be paired with `purge_demo_tenant.py` so the
demo tenant can be re-cycled between Playwright runs.

Output:
    core/backend/tests/fixtures/demo_acme_tenant.json   — canonical seed
    .audit/demo-acme-seed.log                           — append-only journal
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT / "core" / "backend" / "tests" / "fixtures" / "demo_acme_tenant.json"
)
AUDIT_DIR = REPO_ROOT / ".audit"
AUDIT_LOG = AUDIT_DIR / "demo-acme-seed.log"

DEMO_SEED: dict[str, Any] = {
    "tenant_id": "demo-acme",
    "tenant_name": "Demo Acme (Customer Journey)",
    "admin_user": {
        "id": "demo-admin-1",
        "email": "demo@acme.test",
        "roles": ["admin", "member"],
    },
    "projects": [
        {"id": "proj-web", "name": "Web App", "description": "Customer-facing dashboard"},
        {"id": "proj-mobile", "name": "Mobile App", "description": "iOS + Android client"},
        {"id": "proj-internal", "name": "Internal Tool", "description": "Ops automation portal"},
    ],
    "rag_corpus": [
        {
            "doc_id": "demo-handbook-001",
            "format": "md",
            "title": "Acme Q3 OKR Handbook",
            "text": "Q3 OKR: ship multi-tenant beta by 2026-05-15. EUR-only billing. Pricing tiers: Self-host (free), Maintenance ($49/mo), Managed ($499/mo).",
        },
        {
            "doc_id": "demo-handbook-002",
            "format": "md",
            "title": "Customer Onboarding Playbook",
            "text": "Steps: 1) warm intro 2) discovery call 3) DocuSign agreement 4) self-host trial 5) weekly check-in for 30 days.",
        },
        {
            "doc_id": "demo-spec-001",
            "format": "pdf",
            "title": "Web App Architecture Spec (PDF)",
            "text": "FastAPI + Next.js + Caddy. Deployed via Docker Compose. SQLite default, Postgres optional.",
        },
        {
            "doc_id": "demo-spec-002",
            "format": "docx",
            "title": "Mobile App Wireframes (DOCX)",
            "text": "Bottom-tab navigation. Onboarding wizard (3 steps). Push via APNs + FCM.",
        },
        {
            "doc_id": "demo-policy-001",
            "format": "md",
            "title": "Internal Tool Access Policy",
            "text": "Only tenant admins can promote a workflow from draft to published. Cerbos enforces.",
        },
    ],
    "meetings": [
        {
            "meeting_id": "mtg-001",
            "title": "Q3 kick-off",
            "transcript": "[Esra] Ekibe Q3 OKR'yi hatırlatmalıyım.\n[Mert] Pricing sayfası canlıya çıkacak mı?\n[Esra] Evet, 15 Mayıs hedef.\n[Mert] Sözleşmeyi bu hafta gönder.\n",
        },
        {
            "meeting_id": "mtg-002",
            "title": "Mobile App design review",
            "transcript": "[Mert] Onboarding adımları üç tane mi olsun?\n[Esra] Üç yeterli, dördüncü kullanıcı yoruyor.\n[Mert] APNs key'i Operations'tan ister misin?\n",
        },
        {
            "meeting_id": "mtg-003",
            "title": "Customer Success weekly",
            "transcript": "[CSM] Demo Acme self-host trial'ı başladı, ilk hafta çağrısı Salı.\n[Esra] Weekly check-in oluştur.\n",
        },
    ],
    "linear_tickets": [
        {"id": "TKT-101", "title": "Pricing page i18n", "status": "in_progress", "owner": "esra"},
        {"id": "TKT-102", "title": "Mobile push key rotation", "status": "todo", "owner": "mert"},
        {"id": "TKT-103", "title": "Self-host trial follow-up", "status": "todo", "owner": "csm"},
        {"id": "TKT-104", "title": "Workflow draft → publish RBAC", "status": "review", "owner": "engr"},
        {"id": "TKT-105", "title": "Q3 OKR retro", "status": "todo", "owner": "esra"},
    ],
    "expected": {
        "rag_query_examples": [
            {"q": "What is Acme's Q3 goal?", "must_contain": ["multi-tenant", "2026-05-15"]},
            {"q": "Onboarding steps?", "must_contain": ["DocuSign", "self-host"]},
        ],
    },
}


def fingerprint(payload: dict[str, Any]) -> str:
    """Deterministic sha256 — used by the idempotency check."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_seed(*, force: bool = False) -> tuple[str, bool]:
    """Write the seed fixture if missing or out of date.

    Returns (fingerprint, written) where `written` is True iff the file
    changed on disk. Idempotent: re-running on identical content is a no-op.
    """
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_fp = fingerprint(DEMO_SEED)
    if FIXTURE_PATH.exists() and not force:
        existing = json.loads(FIXTURE_PATH.read_text())
        if fingerprint(existing) == new_fp:
            return new_fp, False
    FIXTURE_PATH.write_text(json.dumps(DEMO_SEED, indent=2, ensure_ascii=False) + "\n")
    return new_fp, True


def append_audit(action: str, fp: str, written: bool) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "action": action,
            "tenant_id": DEMO_SEED["tenant_id"],
            "fingerprint": fp,
            "written": written,
        }
    )
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the fixture even if fingerprints match",
    )
    parser.add_argument(
        "--print-fingerprint",
        action="store_true",
        help="Emit only the fingerprint (used by tests)",
    )
    args = parser.parse_args(argv)

    fp, written = write_seed(force=args.force)
    append_audit("seed", fp, written)
    if args.print_fingerprint:
        print(fp)
    else:
        action = "WROTE" if written else "UNCHANGED"
        print(f"{action} {FIXTURE_PATH.relative_to(REPO_ROOT)} fingerprint={fp[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
