"""auth_device_grants — device-authorization grant (RFC 8628 shape) so the
ABS desktop editor can sign in with a short code approved in the browser.

Revision ID: 0029_device_grant
Revises: 0028_meeting_audio_fingerprint
Create Date: 2026-07-30

The device code is stored only as a SHA-256 digest; the human-facing user
code is short-lived (10 min TTL) and single-use. The redeemed credential is
an ``abs_mcp_`` integration token recorded in minted_token_record.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029_device_grant"
down_revision: Union[str, None] = "0028_meeting_audio_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_device_grants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_code_hash", sa.String(64), nullable=False),
        sa.Column("user_code", sa.String(16), nullable=False),
        sa.Column("scopes", sa.String(512), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_subject", sa.String(254), nullable=True),
        sa.Column("approved_tenant", sa.String(64), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_device_grants_device_code_hash",
        "auth_device_grants",
        ["device_code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_device_grants_user_code", "auth_device_grants", ["user_code"]
    )
    op.create_index(
        "ix_auth_device_grants_expires_at", "auth_device_grants", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("auth_device_grants")
