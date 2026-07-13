# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.3 — feature_usage 29-ID catalog + tenant aggregation service.

29 feature IDs are the immutable "what we measure" registry. Adding a new
feature requires a code change here AND a release note (so it shows up in
analytics dashboards and per-tier quota plans).

Aggregation: SQLite has no materialized views, so `get_usage()` runs a
GROUP BY at query time. For self-host deployments (<= 1M rows) this is
sub-millisecond; if a tenant outgrows it, the aggregation can be moved to a
periodic snapshot table without changing the public API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlmodel import Session, func, select

from app.db.models import FeatureUsageLog
from app.db.session import get_engine

logger = logging.getLogger(__name__)


FEATURE_IDS: tuple[str, ...] = (
    "mcp_call",
    "rag_query",
    "workflow_run",
    "marketplace_install",
    "marketplace_view",
    "audio_upload",
    "tts_synthesize",
    "transcribe_meetily",
    "quota_check",
    "user_login",
    "user_signup",
    "admin_dashboard_view",
    "audit_log_view",
    "vault_audit",
    "license_check",
    "smart_link_github",
    "smart_link_slack",
    "smart_link_gmail",
    "smart_link_linear",
    "cascade_provider_call",
    "race_pattern",
    "qual_pipeline",
    "judge_disagreement",
    "schema_export",
    "schema_import",
    "tenant_purge",
    "tenant_export",
    "consent_withdraw",
    "magic_link_claim",
)
assert len(FEATURE_IDS) == 29, (
    "FEATURE_IDS must stay at 29 — bump migration if you change."
)


def is_known(feature_id: str) -> bool:
    return feature_id in FEATURE_IDS


def increment(
    feature_id: str,
    tenant_slug: str = "default",
    actor_email: Optional[str] = None,
) -> None:
    """Append a single usage event. Unknown feature_id raises ValueError so
    typos surface during integration; never crashes a request path —
    callers should wrap in a `try/except` if telemetry is best-effort.
    """
    if feature_id not in FEATURE_IDS:
        raise ValueError(f"unknown feature_id: {feature_id}")
    row = FeatureUsageLog(
        tenant_slug=tenant_slug,
        feature_id=feature_id,
        actor_email=actor_email,
        ts=datetime.now(timezone.utc),
    )
    try:
        with Session(get_engine()) as db:
            db.add(row)
            db.commit()
    except Exception as exc:
        # Telemetry failures must not break business flows.
        logger.debug("feature_usage write failed: %s", exc)


def get_usage(
    tenant_slug: str = "default",
    feature_ids: Optional[Iterable[str]] = None,
) -> List[dict]:
    """Return [{feature_id, count, last_used_at}, ...] for the catalogue
    (or filtered subset). Features that have never been used appear with
    `count=0` and `last_used_at=None` so dashboards always render the full
    matrix.
    """
    requested = list(feature_ids) if feature_ids else list(FEATURE_IDS)
    rows: dict[str, dict] = {
        fid: {"feature_id": fid, "count": 0, "last_used_at": None} for fid in requested
    }
    try:
        with Session(get_engine()) as db:
            stmt = (
                select(
                    FeatureUsageLog.feature_id,
                    func.count(FeatureUsageLog.id).label("cnt"),
                    func.max(FeatureUsageLog.ts).label("last"),
                )
                .where(FeatureUsageLog.tenant_slug == tenant_slug)
                .group_by(FeatureUsageLog.feature_id)
            )
            for fid, cnt, last in db.execute(stmt).all():
                if fid not in rows:
                    continue
                rows[fid]["count"] = int(cnt or 0)
                rows[fid]["last_used_at"] = last.isoformat() if last else None
    except Exception as exc:
        logger.debug("feature_usage read failed: %s", exc)
    return list(rows.values())
