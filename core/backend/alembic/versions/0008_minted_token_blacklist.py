"""Q10-L6-002 / Q11-L14-001 — minted_token_blacklist table.

Revision ID: 0008_minted_token_blacklist
Revises: 0007_chat_sessions
Create Date: 2026-05-01

Q10 Round 14 added the MintedTokenBlacklist SQLModel + the
/v1/mcp/tokens/revoke + /v1/mcp/tokens/revoked endpoints, but no
Alembic migration. Test environments stand the table up via
SQLModel.metadata.create_all(), but production deployments that
upgrade via `alembic upgrade head` skipped it — the revoke endpoint
silently 500'd on the missing table.

This revision adds the matching DDL so prod ops can roll forward
(and back) deterministically.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_minted_token_blacklist"
down_revision: Union[str, None] = "0007_chat_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "minted_token_blacklist",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "tenant_slug",
            sa.String(64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("label", sa.String(64), nullable=False, server_default=""),
        sa.Column("revoked_by", sa.String(254), nullable=False, server_default=""),
        sa.Column("revoked_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("reason", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_minted_token_blacklist_token_digest",
        "minted_token_blacklist",
        ["token_digest"],
        unique=True,
    )
    op.create_index(
        "ix_minted_token_blacklist_tenant_slug",
        "minted_token_blacklist",
        ["tenant_slug"],
    )
    op.create_index(
        "ix_minted_token_blacklist_revoked_at",
        "minted_token_blacklist",
        ["revoked_at"],
    )
    op.create_index(
        "ix_minted_token_blacklist_expires_at",
        "minted_token_blacklist",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_minted_token_blacklist_expires_at",
        table_name="minted_token_blacklist",
    )
    op.drop_index(
        "ix_minted_token_blacklist_revoked_at",
        table_name="minted_token_blacklist",
    )
    op.drop_index(
        "ix_minted_token_blacklist_tenant_slug",
        table_name="minted_token_blacklist",
    )
    op.drop_index(
        "ix_minted_token_blacklist_token_digest",
        table_name="minted_token_blacklist",
    )
    op.drop_table("minted_token_blacklist")
