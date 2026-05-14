"""Sprint 2I UAT-041 — failed_login_attempt table for brute-force defense.

Revision ID: 0013_failed_login_attempts
Revises: 0012_tenant_settings_and_fk_cascades
Create Date: 2026-05-14

The /auth/login endpoint had no rate limit or per-email backoff. This
migration introduces ``failed_login_attempts`` so each unsuccessful login
records (email, tenant_slug, attempts_count, last_attempt_at, locked_until).
Combined with the ``@limiter.limit("5/minute")`` decorator on the route,
this turns the 1000-passwords-per-minute brute force into a 5/min IP cap
plus per-email exponential lockout.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_failed_login_attempts"
down_revision: Union[str, None] = "0012_tenant_settings_and_fk_cascades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failed_login_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("tenant_slug", sa.String(64), nullable=True),
        sa.Column("attempts_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_failed_login_attempts_email",
        "failed_login_attempts",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_failed_login_attempts_locked_until",
        "failed_login_attempts",
        ["locked_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_failed_login_attempts_locked_until",
        table_name="failed_login_attempts",
    )
    op.drop_index(
        "ix_failed_login_attempts_email",
        table_name="failed_login_attempts",
    )
    op.drop_table("failed_login_attempts")
