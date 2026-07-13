"""minted_token_record — issuance ledger so the panel can list + revoke
multiple active MCP tokens (digest only, never the raw token).

Revision ID: 0027_minted_token_record
Revises: 0026_action_outbox
Create Date: 2026-06-17

MCP tokens stay HMAC-stateless for verification; this table only records
issuance metadata (digest, label, scope, issued/expiry) so the operator can see
and individually revoke each token. Revocation status is derived by joining
minted_token_blacklist on token_digest. Admin-scoped (like the blacklist), so
no RLS — queries filter by tenant_slug.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0027_minted_token_record"
down_revision: Union[str, None] = "0026_action_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "minted_token_record",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("label", sa.String(64), nullable=False, server_default=""),
        sa.Column("scope", sa.String(64), nullable=False, server_default="all"),
        sa.Column("issued_by", sa.String(254), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_minted_token_record_token_digest",
        "minted_token_record",
        ["token_digest"],
        unique=True,
    )
    op.create_index(
        "ix_minted_token_record_tenant_slug", "minted_token_record", ["tenant_slug"]
    )
    op.create_index(
        "ix_minted_token_record_issued_at", "minted_token_record", ["issued_at"]
    )
    op.create_index(
        "ix_minted_token_record_expires_at", "minted_token_record", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("minted_token_record")
