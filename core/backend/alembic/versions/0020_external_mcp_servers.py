"""External MCP federation — external_mcp_servers table (+ RLS).

Revision ID: 0020_external_mcp
Revises: 0018_project_slug_per_tenant
Create Date: 2026-06-08

A tenant registers a third-party MCP server (GitHub / Slack / their own) from
the panel; ABS connects to it as an MCP *client* and federates its tools. The
``encrypted_auth`` column holds a Fernet ciphertext of the bearer/header value
(app.multitenant.crypto) — never the plaintext. Tenant-scoped; RLS like the
audit-table policies. SQLite (digisfer self-host + the test lane) no-ops the RLS
steps and gets the table via SQLModel ``create_all``.

Chains off 0018 (the deployed digisfer head) as a self-contained change — the
RLS-extension and agentic-growth migrations are separate workstreams that are
not part of this deployment.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020_external_mcp"
down_revision: Union[str, None] = "0018_project_slug_per_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "external_mcp_servers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False, server_default="default"),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False, server_default="http"),
        sa.Column("auth_type", sa.String(16), nullable=False, server_default="none"),
        sa.Column("encrypted_auth", sa.String(8192), nullable=False, server_default=""),
        sa.Column("header_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(24), nullable=False, server_default="unconfigured"),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("discovered_tool_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(254), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_slug", "slug", name="uq_external_mcp_tenant_slug"),
    )
    op.create_index(
        "ix_external_mcp_servers_tenant_slug", "external_mcp_servers", ["tenant_slug"]
    )
    op.create_index(
        "ix_external_mcp_servers_slug", "external_mcp_servers", ["slug"]
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE external_mcp_servers ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE external_mcp_servers FORCE ROW LEVEL SECURITY;")
        op.execute(
            "CREATE POLICY external_mcp_servers_tenant_isolation ON external_mcp_servers "
            f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS external_mcp_servers_tenant_isolation ON external_mcp_servers;"
        )
        op.execute("ALTER TABLE external_mcp_servers NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE external_mcp_servers DISABLE ROW LEVEL SECURITY;")
    op.drop_table("external_mcp_servers")
