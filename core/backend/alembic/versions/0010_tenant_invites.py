"""tenant_invites table for the admin invite flow.

Revision ID: 0010_tenant_invites
Revises: 0009_chat_threading
Create Date: 2026-05-10

Adds ``tenant_invites`` so ``POST /v1/admin/users/invite`` can persist a
pending invite + magic-link hash. The magic-link plaintext is mailed to
the recipient; only the HMAC-SHA256 digest of the token is stored here
so a database read can't recover a usable token.

Indexes:
  ix_tenant_invites_invite_id            unique  → revoke / lookup
  ix_tenant_invites_email                        → duplicate detection
  ix_tenant_invites_tenant_status                → list endpoint filter
  ix_tenant_invites_magic_token_hash     unique  → /auth/magic consume
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010_tenant_invites"
down_revision: Union[str, None] = "0009_chat_threading"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DateTime(timezone=True) so Postgres
    # ships TIMESTAMP WITH TIME ZONE (SQLite ignores tz, idempotent);
    # CheckConstraint on role/status as defense-in-depth in case the
    # Pydantic Literal is bypassed via a low-level UPDATE.
    #
    # FK to tenants.slug was considered but skipped: the codebase ships
    # a "default" tenant slug as the bootstrap fallback that doesn't
    # always have a matching tenants row, so a NOT NULL FK would
    # regress existing flows. Application-level tenant resolution is
    # sufficient until the formal tenant lifecycle lands.
    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invite_id", sa.String(24), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("invited_by", sa.String(255), nullable=False),
        sa.Column("magic_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'member', 'operator', 'viewer')",
            name="ck_tenant_invites_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_tenant_invites_status",
        ),
    )
    op.create_index(
        "ix_tenant_invites_invite_id",
        "tenant_invites",
        ["invite_id"],
        unique=True,
    )
    op.create_index("ix_tenant_invites_email", "tenant_invites", ["email"])
    op.create_index(
        "ix_tenant_invites_tenant_status",
        "tenant_invites",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_tenant_invites_magic_token_hash",
        "tenant_invites",
        ["magic_token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_invites_magic_token_hash", table_name="tenant_invites")
    op.drop_index("ix_tenant_invites_tenant_status", table_name="tenant_invites")
    op.drop_index("ix_tenant_invites_email", table_name="tenant_invites")
    op.drop_index("ix_tenant_invites_invite_id", table_name="tenant_invites")
    op.drop_table("tenant_invites")
