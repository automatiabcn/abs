"""Phase 4 — usage_log table for provider quota aggregation.

Revision ID: 0005_usage_log
Revises: 0004_sprint20_meetings
Create Date: 2026-04-29

One row per provider call (or batch) — `provider`, `tokens`, `cost_usd`,
optional `request_id` for cross-correlation. Index on (provider, ts) backs
the monthly aggregation query in quota_monitor.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_usage_log"
down_revision: Union[str, None] = "0004_sprint20_meetings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column(
            "tenant_slug",
            sa.String(64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ts", sa.DateTime, nullable=False),
    )
    op.create_index("ix_usage_log_provider", "usage_log", ["provider"])
    op.create_index("ix_usage_log_tenant_slug", "usage_log", ["tenant_slug"])
    op.create_index("ix_usage_log_ts", "usage_log", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_usage_log_ts", table_name="usage_log")
    op.drop_index("ix_usage_log_tenant_slug", table_name="usage_log")
    op.drop_index("ix_usage_log_provider", table_name="usage_log")
    op.drop_table("usage_log")
