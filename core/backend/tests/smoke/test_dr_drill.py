"""T-062 — DR drill smoke checks.

These tests run AFTER `scripts/dr/dr_drill.sh` restores from a snapshot. They
verify the application boots, the alembic head matches what the migration chain
expects, and that a representative tenant row survives the round-trip.

Run with: `pytest tests/smoke -k dr_drill`.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("ABS_ENV") != "staging",
    reason="DR drill smoke runs only in staging post-restore.",
)


def test_alembic_head_is_known() -> None:
    """The head revision id must be a value emitted by our migration tree."""
    from sqlalchemy import create_engine, text

    url = os.environ["ABS_PG_URL"]
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert head in {
        "0000_init_baseline",
        "0001_oauth_baseline",
        "0002_oauth_extra_claims",
        "0003_tenant_projects",
    }


def test_tenant_table_has_rows() -> None:
    """At least one tenant must survive the restore — drilling against an empty
    DB would not actually exercise the data path we care about."""
    from sqlalchemy import create_engine, text

    url = os.environ["ABS_PG_URL"]
    engine = create_engine(url)
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
    assert n is not None
    assert n >= 1, "DR drill requires at least one tenant in staging fixtures"


def test_health_endpoint_after_restore() -> None:
    """Backend must respond 200 on /healthz after the DR cycle."""
    import urllib.request

    base = os.environ.get("ABS_BASE_URL", "http://abs-abs-backend:8000")
    with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
        assert resp.status == 200
