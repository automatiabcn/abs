"""workflow_schedule — the row that makes a saved cron actually fire.

Revision ID: 0030_workflow_schedule
Revises: 0029_device_grant
Create Date: 2026-07-30

The workflow ontology could always describe a cron trigger and nothing ran it.
This table is what the scheduler ticks over: `next_run_at` doubles as the claim
token, so two replicas ticking at the same second cannot run one schedule twice.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0030_workflow_schedule"
down_revision: Union[str, None] = "0029_device_grant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_schedule",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False, server_default="default"),
        sa.Column("workflow_id", sa.Integer, nullable=False),
        sa.Column("cron_expr", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_error", sa.String(400), nullable=True),
        sa.Column("created_by", sa.String(254), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_schedule_tenant_slug", "workflow_schedule", ["tenant_slug"])
    op.create_index("ix_workflow_schedule_workflow_id", "workflow_schedule", ["workflow_id"])
    op.create_index("ix_workflow_schedule_enabled", "workflow_schedule", ["enabled"])
    # The tick selects on this column, and claims by writing it.
    op.create_index("ix_workflow_schedule_next_run_at", "workflow_schedule", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("workflow_schedule")
