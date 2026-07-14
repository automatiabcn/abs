"""Create the abs_admin Postgres role that owns BYPASSRLS.

Revision ID: 0015b_abs_admin_role
Revises: 0015_rls_audit_tables
Create Date: 2026-05-14

Production deploy notes — ``docs/operations/rls-admin-bypass.md`` — go
into the GRANT and DSN switch the founder runs once on the Hetzner
cluster. This migration *only* creates the role so the application's
schema is self-describing and matches infra-as-code.

The role is created with ``NOLOGIN`` by default. The founder grants
login + connect access during deploy; before that the role exists but
nothing can authenticate as it, which keeps an unfinished prod deploy
safe from inadvertent admin connections.

SQLite path: skip — there is no role concept.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0015b_abs_admin_role"
down_revision: Union[str, None] = "0015_rls_audit_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        return

    # Idempotent role create — DO block keeps re-runs harmless on a
    # cluster where the role already exists (e.g. cloning a prod DB
    # into staging and re-applying head).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'abs_admin'
            ) THEN
                CREATE ROLE abs_admin WITH BYPASSRLS NOLOGIN NOINHERIT;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        return

    # DROP ROLE fails when the role still owns objects; we intentionally
    # let that surface as an error so a downgrade against a live prod
    # admin connection does not silently strip the role and orphan its
    # grants. Staging / dev clusters can DROP cleanly.
    op.execute("DROP ROLE IF EXISTS abs_admin;")
