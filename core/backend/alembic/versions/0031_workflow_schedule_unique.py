"""workflow_schedule — one schedule per (tenant, workflow), enforced.

Revision ID: 0031_workflow_schedule_unique
Revises: 0030_workflow_schedule
Create Date: 2026-07-31

`set_schedule` reads-then-writes; two concurrent calls could both see no row
and insert two schedules for the same workflow. Each row is claimed
independently by the tick, so a duplicate pair means the workflow runs twice
at every due time. The atomic `next_run_at` claim only protects a single row —
row multiplicity needs the database to refuse it.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0031_workflow_schedule_unique"
down_revision: Union[str, None] = "0030_workflow_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any duplicates the race already produced, keeping the oldest row
    # (the one whose next_run_at claim history is longest).
    op.execute(
        sa.text(
            "DELETE FROM workflow_schedule WHERE id NOT IN ("
            "SELECT MIN(id) FROM workflow_schedule "
            "GROUP BY tenant_slug, workflow_id)"
        )
    )
    # A unique index (not a table constraint) works unchanged on SQLite and
    # Postgres without batch-rebuilding the table.
    op.create_index(
        "uq_workflow_schedule_tenant_wf",
        "workflow_schedule",
        ["tenant_slug", "workflow_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_schedule_tenant_wf", table_name="workflow_schedule")
