# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""028 Modul H — `security_audit` MCP tool.

Aggregates security-relevant signals across the system:
  - webhook secrets configured + last rotation timestamp
  - active OAuth state token count (CSRF in flight)
  - rate-limit 429 count last 24h
  - vault audit chain status (027 integration)
  - TLS cert expiry days (best-effort, runs only on production hosts)
  - overall_score: ok | warn | danger
"""

from __future__ import annotations

import json
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


def _last_rotation_days_ago() -> int | None:
    try:
        from sqlmodel import Session, select

        from app.db.models import VaultAuditEntry
        from app.db.session import get_engine

        from datetime import datetime, timezone

        with Session(get_engine()) as s:
            row = s.scalars(
                select(VaultAuditEntry)
                .where(VaultAuditEntry.action == "rotate")
                .order_by(VaultAuditEntry.id.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            if row is None:
                return None
            ts = row.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts).days
    except Exception:
        return None


@mcp_server.tool()
@with_hooks("security_audit")
async def security_audit() -> str:
    """028 — Aggregate security signals (admin-grade dashboard)."""
    await tracker.bump("security_audit")
    from app.config import settings
    from app.middleware.rate_limit import breach_count_24h
    from app.vault.audit_chain import stats as audit_stats
    from sqlmodel import Session, select

    from app.db.models import OAuthState
    from app.db.session import get_engine

    secrets_status = {
        "stripe_set": bool(settings.stripe_webhook_secret),
        "slack_set": bool(settings.slack_signing_secret),
        "github_app_set": bool(settings.github_app_webhook_secret),
        "last_rotated_days_ago": _last_rotation_days_ago(),
    }

    with Session(get_engine()) as s:
        active_states = len(s.scalars(select(OAuthState)).all())

    breaches = breach_count_24h()
    audit = audit_stats(recent_limit=5)

    danger_signals = 0
    warn_signals = 0
    if not secrets_status["stripe_set"]:
        warn_signals += 1
    if not secrets_status["slack_set"]:
        warn_signals += 1
    if breaches > 100:
        danger_signals += 1
    elif breaches > 10:
        warn_signals += 1
    if audit["audit_chain_integrity"] != "ok":
        danger_signals += 1
    last_rot = secrets_status["last_rotated_days_ago"]
    if last_rot is not None and last_rot > 365:
        warn_signals += 1

    if danger_signals > 0:
        overall = "danger"
    elif warn_signals > 0:
        overall = "warn"
    else:
        overall = "ok"

    return json.dumps(
        {
            "webhook_secrets": secrets_status,
            "oauth_active_states": active_states,
            "rate_limit_breaches_24h": breaches,
            "vault_audit": {
                "integrity": audit["audit_chain_integrity"],
                "total_entries": audit["total_entries"],
                "tampered_entry_id": audit["tampered_entry_id"],
            },
            "tls_cert_expires_days": None,  # placeholder (production: read from Caddy admin API)
            "overall_score": overall,
        },
        ensure_ascii=False,
        indent=2,
    )


REGISTERED_TOOLS.extend(["security_audit"])
