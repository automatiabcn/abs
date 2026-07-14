"""OAuth 2.1 server tables (clients, auth codes, refresh tokens).

Revision ID: 0001_oauth_baseline
Revises: 0000_init_baseline
Create Date: 2026-04-27

Depends on 0000_init_baseline which captures the legacy
pre-OAuth ABS schema. Existing deployments still on `create_all()`
should `alembic stamp 0000_init_baseline` first, then upgrade head.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_oauth_baseline"
down_revision: Union[str, None] = "0000_init_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("client_secret_hash", sa.String(128), nullable=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("redirect_uris", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "allowed_scopes",
            sa.String(512),
            nullable=False,
            server_default="openid profile",
        ),
        sa.Column(
            "is_confidential",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_oauth_clients_client_id",
        "oauth_clients",
        ["client_id"],
        unique=True,
    )

    op.create_table(
        "oauth_auth_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("user_subject", sa.String(128), nullable=False),
        sa.Column("redirect_uri", sa.String(512), nullable=False),
        sa.Column("scope", sa.String(512), nullable=False, server_default=""),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column(
            "code_challenge_method",
            sa.String(8),
            nullable=False,
            server_default="S256",
        ),
        sa.Column("nonce", sa.String(128), nullable=True),
        sa.Column("issued_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_oauth_auth_codes_code",
        "oauth_auth_codes",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_auth_codes_client_id",
        "oauth_auth_codes",
        ["client_id"],
    )
    op.create_index(
        "ix_oauth_auth_codes_used_at",
        "oauth_auth_codes",
        ["used_at"],
    )

    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("user_subject", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(512), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("rotated_to_hash", sa.String(128), nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_oauth_refresh_tokens_token_hash",
        "oauth_refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_refresh_tokens_client_id",
        "oauth_refresh_tokens",
        ["client_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_refresh_tokens_client_id", "oauth_refresh_tokens")
    op.drop_index("ix_oauth_refresh_tokens_token_hash", "oauth_refresh_tokens")
    op.drop_table("oauth_refresh_tokens")

    op.drop_index("ix_oauth_auth_codes_used_at", "oauth_auth_codes")
    op.drop_index("ix_oauth_auth_codes_client_id", "oauth_auth_codes")
    op.drop_index("ix_oauth_auth_codes_code", "oauth_auth_codes")
    op.drop_table("oauth_auth_codes")

    op.drop_index("ix_oauth_clients_client_id", "oauth_clients")
    op.drop_table("oauth_clients")
