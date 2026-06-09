"""Connector Layer — connector_states table (+ RLS).

Revision ID: 0022_connector_states
Revises: 0021_growth_domain
Create Date: 2026-06-08

Per-tenant connection state for catalog connectors. Tenant-scoped; RLS like
0019-0021. SQLite no-ops the RLS steps (tables created via create_all).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0022_connector_states"
down_revision: Union[str, None] = "0021_growth_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "connector_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False, server_default="default"),
        sa.Column("connector_id", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="connected"),
        sa.Column("health", sa.Integer, nullable=False, server_default="100"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_connector_states_tenant_slug", "connector_states", ["tenant_slug"])
    op.create_index("ix_connector_states_connector_id", "connector_states", ["connector_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE connector_states ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE connector_states FORCE ROW LEVEL SECURITY;")
        op.execute(
            "CREATE POLICY connector_states_tenant_isolation ON connector_states "
            f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS connector_states_tenant_isolation ON connector_states;")
        op.execute("ALTER TABLE connector_states NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE connector_states DISABLE ROW LEVEL SECURITY;")
    op.drop_table("connector_states")
