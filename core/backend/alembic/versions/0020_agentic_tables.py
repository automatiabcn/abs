"""Agentic Growth — agent_runs + approval_items tables (+ RLS).

Revision ID: 0020_agentic_tables
Revises: 0019_rls_tenant_tables
Create Date: 2026-06-08

Creates the two agentic-core tables (`agent_runs` = every agent execution,
`approval_items` = the DB-backed Approval Center) and enrols both in the same
tenant RLS policy as 0019. Both are written only inside an authenticated
request, where the tenant-context middleware has pinned the GUC. SQLite (tests +
digisfer self-host) creates the tables via `SQLModel.metadata.create_all`; the
RLS steps no-op there.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020_agentic_tables"
down_revision: Union[str, None] = "0019_rls_tenant_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"
_RLS_TABLES = ("agent_runs", "approval_items")


def _enable_rls(tbl: str) -> None:
    op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
        f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
    )


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False, server_default="default"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("task", sa.String(8000), nullable=False),
        sa.Column("summary", sa.String(4096), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("risk", sa.String(16), nullable=False, server_default="low"),
        sa.Column("requires_approval", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("elapsed_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actor", sa.String(254), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_runs_tenant_slug", "agent_runs", ["tenant_slug"])
    op.create_index("ix_agent_runs_agent_id", "agent_runs", ["agent_id"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    op.create_table(
        "approval_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False, server_default="default"),
        sa.Column("agent_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("agent_run_id", sa.Integer, nullable=True),
        sa.Column("action", sa.String(1024), nullable=False),
        sa.Column("target_company", sa.String(256), nullable=False, server_default=""),
        sa.Column("target_person", sa.String(256), nullable=False, server_default=""),
        sa.Column("channel", sa.String(64), nullable=False, server_default=""),
        sa.Column("rationale", sa.String(4096), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("proposed_message", sa.String(8192), nullable=False, server_default=""),
        sa.Column("risk", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("consent_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("policy_result", sa.String(64), nullable=False, server_default="requires_approval"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(254), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalate_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approval_items_tenant_slug", "approval_items", ["tenant_slug"])
    op.create_index("ix_approval_items_agent_id", "approval_items", ["agent_id"])
    op.create_index("ix_approval_items_agent_run_id", "approval_items", ["agent_run_id"])
    op.create_index("ix_approval_items_status", "approval_items", ["status"])
    op.create_index("ix_approval_items_created_at", "approval_items", ["created_at"])

    if op.get_bind().dialect.name == "postgresql":
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for tbl in _RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
    op.drop_table("approval_items")
    op.drop_table("agent_runs")
