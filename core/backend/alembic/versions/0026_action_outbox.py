"""Stage D + E schema — action_executions outbox, agentic_workflow_defs,
connector_states credential columns.

Revision ID: 0026_action_outbox
Revises: 0025_merge_agentic_mcp
Create Date: 2026-06-09

- action_executions: the consent-gated 'onay → aksiyon' outbox/audit (Stage E).
- agentic_workflow_defs: the saved Workflow Designer graph (Stage D).
- connector_states: real-integration credential columns (Stage A).
All tenant-scoped; RLS on the new tables like 0019-0024. SQLite no-ops RLS.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0026_action_outbox"
down_revision: Union[str, None] = "0025_merge_agentic_mcp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"


def _enable_rls(table: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
        )


def _disable_rls(table: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


def upgrade() -> None:
    # ── Stage E — action_executions outbox ──────────────────────────────────
    op.create_table(
        "action_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("approval_item_id", sa.Integer, nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "action_kind", sa.String(32), nullable=False, server_default="internal"
        ),
        sa.Column("channel", sa.String(32), nullable=False, server_default=""),
        sa.Column("target_company", sa.String(256), nullable=False, server_default=""),
        sa.Column("target_contact", sa.String(254), nullable=False, server_default=""),
        sa.Column("message", sa.String(2048), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="executed"),
        sa.Column("reason", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_action_executions_tenant_slug", "action_executions", ["tenant_slug"]
    )
    op.create_index(
        "ix_action_executions_approval_item_id",
        "action_executions",
        ["approval_item_id"],
    )
    op.create_index("ix_action_executions_status", "action_executions", ["status"])
    op.create_index(
        "ix_action_executions_created_at", "action_executions", ["created_at"]
    )
    _enable_rls("action_executions")

    # ── Stage D — agentic_workflow_defs ─────────────────────────────────────
    op.create_table(
        "agentic_workflow_defs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("key", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("graph_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agentic_workflow_defs_tenant_slug", "agentic_workflow_defs", ["tenant_slug"]
    )
    op.create_index("ix_agentic_workflow_defs_key", "agentic_workflow_defs", ["key"])
    _enable_rls("agentic_workflow_defs")

    # ── Stage A — connector_states real-integration columns ─────────────────
    op.add_column(
        "connector_states",
        sa.Column("auth_kind", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column(
        "connector_states",
        sa.Column(
            "encrypted_credentials", sa.String(8192), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "connector_states",
        sa.Column("last_sync_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "connector_states", sa.Column("last_error", sa.String(512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("connector_states", "last_error")
    op.drop_column("connector_states", "last_sync_count")
    op.drop_column("connector_states", "encrypted_credentials")
    op.drop_column("connector_states", "auth_kind")

    _disable_rls("agentic_workflow_defs")
    op.drop_table("agentic_workflow_defs")

    _disable_rls("action_executions")
    op.drop_table("action_executions")
