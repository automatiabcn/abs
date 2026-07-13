# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (f) — 3rd-eye logic audit.

Regression: ``_data_export_counts`` compared a DataExportJob.expires_at (tz-naive
on SQLite round-trip) against a tz-aware ``now``. The ``naive < aware`` TypeError
was silently swallowed by the function's outer try/except, so an expired export
job was miscounted (the loop aborted). Now the expires_at is normalized to UTC,
matching billing_tools / me_data_export.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.db.models import DataExportJob
from app.db.session import get_engine
from app.mcp.tools.compliance_tools import _data_export_counts


def test_naive_expired_export_job_is_counted_not_swallowed(client):
    # tz-NAIVE past expiry — exactly what SQLite returns for a stored datetime.
    with Session(get_engine()) as db:
        db.add(
            DataExportJob(
                job_id="exp-tz-naive-1",
                license_jti="jti-x",
                customer_email="a@x.io",
                status="done",
                expires_at=datetime(2020, 1, 1, 0, 0, 0),  # naive, in the past
            )
        )
        db.commit()

    counts = _data_export_counts()
    # Before the fix the TypeError was swallowed and this stayed 0.
    assert counts["expired"] >= 1
