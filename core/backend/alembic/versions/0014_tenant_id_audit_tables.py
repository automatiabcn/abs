"""Add tenant_id column to 3 audit tables (RLS preparation).

Revision ID: 0014_tenant_id_audit_tables
Revises: 0013_failed_login_attempts
Create Date: 2026-05-14

Adds a ``tenant_id`` column (NOT NULL, default ``'_unknown'``) plus an
index on each of the three audit tables that the RLS layer
guards:

    - customer_audit_entries
    - webhook_events
    - vault_audit_entries

The follow-up data migration ``0014b_backfill_tenant_id`` populates the
column from existing relations; the policy migration
``0015_rls_audit_tables`` then enables + forces RLS once the column is
non-default.

The ``server_default='_unknown'`` lets the migration land safely on a
database with live rows. Backfill removes those sentinels in step two;
any row that the heuristic cannot resolve stays ``_unknown`` and is
flagged for manual review (see ``docs/operations/rls-admin-bypass.md``).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014_tenant_id_audit_tables"
down_revision: Union[str, None] = "0013_failed_login_attempts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES: tuple[str, ...] = (
    "customer_audit_entries",
    "webhook_events",
    "vault_audit_entries",
)


def upgrade() -> None:
    for tbl in TABLES:
        op.add_column(
            tbl,
            sa.Column(
                "tenant_id",
                sa.String(64),
                nullable=False,
                server_default="_unknown",
            ),
        )
        op.create_index(
            f"ix_{tbl}_tenant_id",
            tbl,
            ["tenant_id"],
        )


def downgrade() -> None:
    for tbl in TABLES:
        op.drop_index(f"ix_{tbl}_tenant_id", table_name=tbl)
        op.drop_column(tbl, "tenant_id")
