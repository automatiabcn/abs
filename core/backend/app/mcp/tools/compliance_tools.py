# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""`compliance_status` MCP tool.

Aggregates GDPR-relevant signals into a single dashboard payload:
  - audit_log_retention_days   (config + actual oldest row age)
  - data_export_jobs           (queued/done/expired counts)
  - pending_deletions          (count of licenses with scheduled_delete_at)
  - purged_accounts            (lifetime count)
  - consents                   (per-type granted/withdrawn counts)
  - dpa_template_present       (docs/legal/dpa-template.md exists?)
  - privacy_policy_present     (frontend/src/app/privacy/page.tsx exists?)
  - subprocessors_listed       (docs/legal/subprocessors.md exists?)
  - overall_status             ok | warn | gap
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402

try:
    REPO_ROOT = Path(__file__).resolve().parents[5]
except IndexError:
    # Container layout differs from monorepo (parents[5] OOB) — fall back to env or /app.
    import os as _os

    REPO_ROOT = Path(_os.environ.get("ABS_REPO_ROOT", "/app"))
DPA_PATH = REPO_ROOT / "docs" / "legal" / "dpa-template.md"
SUBPROCESSORS_PATH = REPO_ROOT / "docs" / "legal" / "subprocessors.md"
PRIVACY_PATH_BACKEND = REPO_ROOT / "docs" / "legal" / "privacy-policy.md"
PRIVACY_PATH_FRONTEND = REPO_ROOT / "core" / "landing" / "app" / "privacy" / "page.tsx"
RETENTION_PATH = REPO_ROOT / "docs" / "data-retention-policy.md"


def _oldest_audit_age_days() -> int | None:
    try:
        from sqlmodel import Session, select

        from app.db.models import CustomerAuditEntry
        from app.db.session import get_engine

        with Session(get_engine()) as s:
            row = s.scalars(
                select(CustomerAuditEntry)
                .order_by(CustomerAuditEntry.ts.asc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            if row is None or row.ts is None:
                return None
            ts = row.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts).days
    except Exception:
        return None


def _data_export_counts() -> dict:
    out = {"queued": 0, "done": 0, "failed": 0, "expired": 0}
    try:
        from sqlmodel import Session, select

        from app.db.models import DataExportJob
        from app.db.session import get_engine

        now = datetime.now(timezone.utc)
        with Session(get_engine()) as s:
            for r in s.scalars(select(DataExportJob)).all():
                key = r.status if r.status in out else "queued"
                # SQLite returns tz-naive datetimes; normalize to UTC before the
                # compare (as billing_tools / me_data_export already do). Without
                # this, `naive < aware` raises TypeError — silently swallowed by
                # the outer try/except, so the counts came out wrong.
                exp = r.expires_at
                if exp is not None and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp and exp < now:
                    out["expired"] += 1
                else:
                    out[key] = out.get(key, 0) + 1
    except Exception:
        pass
    return out


def _deletion_counts() -> dict:
    out = {"pending": 0, "purged": 0}
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as s:
            for r in s.scalars(select(License)).all():
                if r.purged_at is not None:
                    out["purged"] += 1
                elif r.scheduled_delete_at is not None:
                    out["pending"] += 1
    except Exception:
        pass
    return out


def _consent_counts() -> dict:
    out: dict = {}
    try:
        from sqlmodel import Session, select

        from app.db.models import Consent
        from app.db.session import get_engine

        with Session(get_engine()) as s:
            for r in s.scalars(select(Consent)).all():
                bucket = out.setdefault(r.consent_type, {"granted": 0, "withdrawn": 0})
                if r.withdrawn_at is not None:
                    bucket["withdrawn"] += 1
                elif r.granted_at is not None:
                    bucket["granted"] += 1
    except Exception:
        pass
    return out


@mcp_server.tool()
@with_hooks("compliance_status")
async def compliance_status() -> str:
    """029 — GDPR compliance posture dashboard."""
    await tracker.bump("compliance_status")

    docs = {
        "dpa_template_present": DPA_PATH.exists(),
        "subprocessors_listed": SUBPROCESSORS_PATH.exists(),
        "privacy_policy_backend": PRIVACY_PATH_BACKEND.exists(),
        "privacy_policy_frontend": PRIVACY_PATH_FRONTEND.exists(),
        "retention_policy_present": RETENTION_PATH.exists(),
    }

    payload = {
        "audit_log": {
            "retention_days_target": 90,
            "oldest_entry_age_days": _oldest_audit_age_days(),
        },
        "data_export_jobs": _data_export_counts(),
        "deletions": _deletion_counts(),
        "consents": _consent_counts(),
        "docs": docs,
    }

    gap_signals = 0
    warn_signals = 0
    if not docs["dpa_template_present"]:
        gap_signals += 1
    if not docs["privacy_policy_backend"] and not docs["privacy_policy_frontend"]:
        gap_signals += 1
    if not docs["subprocessors_listed"]:
        warn_signals += 1
    if not docs["retention_policy_present"]:
        warn_signals += 1

    if gap_signals > 0:
        overall = "gap"
    elif warn_signals > 0:
        overall = "warn"
    else:
        overall = "ok"
    payload["overall_status"] = overall

    return json.dumps(payload, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["compliance_status"])
