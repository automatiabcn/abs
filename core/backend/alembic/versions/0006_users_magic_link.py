"""Phase 2 / Q3 / Q2.CO5 — users table for magic-link multi-admin signup.

Revision ID: 0006_users_magic_link
Revises: 0005_usage_log
Create Date: 2026-04-29

Adds the `users` table that the `/auth/signup` + `/auth/magic` flow
populates. The bootstrap admin path (admin_credentials.json) is kept as a
fallback so existing /auth/login does not break — see app/api/auth.py
_load_admin_credentials.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_users_magic_link"
down_revision: Union[str, None] = "0005_usage_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column(
            "tenant_slug",
            sa.String(64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("magic_token", sa.String(128), nullable=True),
        sa.Column("magic_expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("claimed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_slug", "users", ["tenant_slug"])
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_magic_token", "users", ["magic_token"])


def downgrade() -> None:
    op.drop_index("ix_users_magic_token", table_name="users")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_tenant_slug", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
