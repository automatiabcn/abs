"""Multi-tenant Phase 1 — provider_keys + project_members tables.

Revision ID: 0016_mt_keys_members
Revises: 0015b_abs_admin_role
Create Date: 2026-06-06

Additive, backward-compatible. Introduces two tables for the multi-tenant data
layer:

  * ``provider_keys`` — per-owner (user|project|org) encrypted provider API key,
    resolved project → user → org → global at request time. Existing global
    keys (settings/vault) keep working; these rows are an opt-in override.
  * ``project_members`` — N-N user↔project membership with a per-project role
    (owner|editor|viewer). Distinct from ``tenant_projects`` (tenant↔project).

No FK CASCADE to tenants.slug — the bootstrap "default" tenant may not have a
``tenants`` row (same rationale as 0011); tenant scoping is enforced in code.
Composite indexes back the upsert/resolution lookups; uniqueness is enforced in
the application layer (SQLite partial-unique inconsistency, per 0011).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016_mt_keys_members"
down_revision: Union[str, None] = "0015b_abs_admin_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_value", sa.String(8192), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_ok", sa.Boolean, nullable=True),
    )
    op.create_index("ix_provider_keys_tenant_slug", "provider_keys", ["tenant_slug"])
    op.create_index("ix_provider_keys_owner_type", "provider_keys", ["owner_type"])
    op.create_index("ix_provider_keys_owner_id", "provider_keys", ["owner_id"])
    op.create_index("ix_provider_keys_provider", "provider_keys", ["provider"])
    op.create_index(
        "ix_provider_keys_lookup",
        "provider_keys",
        ["tenant_slug", "owner_type", "owner_id", "provider"],
    )

    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False),
        sa.Column("project_slug", sa.String(96), nullable=False),
        sa.Column("user_subject", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_project_members_tenant_slug", "project_members", ["tenant_slug"]
    )
    op.create_index(
        "ix_project_members_project_slug", "project_members", ["project_slug"]
    )
    op.create_index(
        "ix_project_members_user_subject", "project_members", ["user_subject"]
    )
    op.create_index(
        "ix_project_members_lookup",
        "project_members",
        ["tenant_slug", "project_slug", "user_subject"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_members_lookup", table_name="project_members")
    op.drop_index("ix_project_members_user_subject", table_name="project_members")
    op.drop_index("ix_project_members_project_slug", table_name="project_members")
    op.drop_index("ix_project_members_tenant_slug", table_name="project_members")
    op.drop_table("project_members")

    op.drop_index("ix_provider_keys_lookup", table_name="provider_keys")
    op.drop_index("ix_provider_keys_provider", table_name="provider_keys")
    op.drop_index("ix_provider_keys_owner_id", table_name="provider_keys")
    op.drop_index("ix_provider_keys_owner_type", table_name="provider_keys")
    op.drop_index("ix_provider_keys_tenant_slug", table_name="provider_keys")
    op.drop_table("provider_keys")
