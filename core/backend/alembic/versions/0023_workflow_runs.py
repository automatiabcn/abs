"""Agentic workflows — workflow_runs table (+ RLS).

Revision ID: 0023_workflow_runs
Revises: 0022_connector_states
Create Date: 2026-06-08

Logs agentic workflow executions (agent chains) for the Workflow Designer run
history. Tenant-scoped; RLS like 0019-0022.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0023_workflow_runs"
down_revision: Union[str, None] = "0022_connector_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("steps_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("result_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="done"),
        sa.Column("step_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("approvals_opened", sa.Integer, nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actor", sa.String(254), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_runs_tenant_slug", "workflow_runs", ["tenant_slug"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE workflow_runs FORCE ROW LEVEL SECURITY;")
        op.execute(
            "CREATE POLICY workflow_runs_tenant_isolation ON workflow_runs "
            f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS workflow_runs_tenant_isolation ON workflow_runs;"
        )
        op.execute("ALTER TABLE workflow_runs NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE workflow_runs DISABLE ROW LEVEL SECURITY;")
    op.drop_table("workflow_runs")
