"""Generic per-tenant settings store (tenant_settings).

Revision ID: 0017_tenant_settings
Revises: 0016_mt_keys_members
Create Date: 2026-06-06

Backs the /admin/settings tabs (webhooks/alerts/security/general). SQLite
deployments create this via SQLModel.metadata.create_all, but Postgres
deployments run `alembic upgrade head` only — so the table needs a migration
to exist there. Additive; one row per (tenant_slug, section).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_tenant_settings"
down_revision: Union[str, None] = "0016_mt_keys_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False),
        sa.Column("section", sa.String(48), nullable=False),
        sa.Column("data_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(254), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_tenant_settings_tenant_slug", "tenant_settings", ["tenant_slug"]
    )
    op.create_index("ix_tenant_settings_section", "tenant_settings", ["section"])
    op.create_index(
        "ix_tenant_settings_lookup", "tenant_settings", ["tenant_slug", "section"]
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_settings_lookup", table_name="tenant_settings")
    op.drop_index("ix_tenant_settings_section", table_name="tenant_settings")
    op.drop_index("ix_tenant_settings_tenant_slug", table_name="tenant_settings")
    op.drop_table("tenant_settings")
