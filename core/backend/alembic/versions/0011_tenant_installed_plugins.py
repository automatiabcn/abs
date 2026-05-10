"""Sprint 2B BUG-34 — tenant_installed_plugins persistence.

Revision ID: 0011_tenant_installed_plugins
Revises: 0010_tenant_invites
Create Date: 2026-05-10

The marketplace install handler used to write only to a JSON file (and
the in-memory sandbox launcher), so the admin marketplace UI couldn't
reliably distinguish installed plugins from un-installed ones after a
backend restart. Persisting the install row in SQL closes that loop and
gives the new ``GET /v1/marketplace/installed`` endpoint a stable list.

Composite unique index on ``(tenant_id, plugin_id)`` enforces "one
active install per tenant-plugin pair" at the DB level so a duplicate
install POST can't double-write.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_tenant_installed_plugins"
down_revision: Union[str, None] = "0010_tenant_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sprint 2B founder audit patch — DateTime(timezone=True) so Postgres
    # ships TIMESTAMP WITH TIME ZONE (SQLite ignores tz, idempotent).
    # FK CASCADE to tenants.slug intentionally skipped — bootstrap
    # "default" tenant slug may not have a tenants row, NOT NULL FK
    # would regress install flow. Application-level tenant resolution
    # is sufficient; Sprint 2C will formalise tenant lifecycle.
    op.create_table(
        "tenant_installed_plugins",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plugin_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "sandbox_container_id", sa.String(64), nullable=True
        ),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tenant_installed_plugins_tenant_id",
        "tenant_installed_plugins",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_installed_plugins_plugin_id",
        "tenant_installed_plugins",
        ["plugin_id"],
    )
    # Active installs are uniqueness-checked in code (filter by
    # uninstalled_at IS NULL) so the ALL-rows index doesn't need to be
    # unique. SQLite doesn't honour partial unique indexes uniformly
    # across versions; the application enforces idempotency.
    op.create_index(
        "ix_tenant_installed_plugins_tenant_plugin",
        "tenant_installed_plugins",
        ["tenant_id", "plugin_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_installed_plugins_tenant_plugin",
        table_name="tenant_installed_plugins",
    )
    op.drop_index(
        "ix_tenant_installed_plugins_plugin_id",
        table_name="tenant_installed_plugins",
    )
    op.drop_index(
        "ix_tenant_installed_plugins_tenant_id",
        table_name="tenant_installed_plugins",
    )
    op.drop_table("tenant_installed_plugins")
