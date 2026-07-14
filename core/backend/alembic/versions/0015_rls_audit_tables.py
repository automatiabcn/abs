"""Enable + force Row Level Security on the 3 audit tables.

Revision ID: 0015_rls_audit_tables
Revises: 0014b_backfill_tenant_id
Create Date: 2026-05-14

Activates Postgres native RLS on:

    - customer_audit_entries
    - webhook_events
    - vault_audit_entries

Policy: a row is visible only when its ``tenant_id`` column matches the
current value of the session GUC ``abs.tenant_id``. The GUC is set by
``app.db.session._set_tenant_guc`` at the start of every cursor execute
from the request ContextVar pinned in ``app.api.v1.tenant_guc``.

ENABLE + FORCE: FORCE applies the policy even to the table owner; this
shuts the door on the historical "ORM connection logs in as the owner
and bypasses the policy" footgun. ``abs_admin`` (created in
``0015b_abs_admin_role``) carries ``BYPASSRLS`` so audit-wide queries
from the operator console still work.

SQLite skip: SQLite has no RLS; the migration silently no-ops there.
The integration tests in ``tests/integration/test_rls_audit_tables.py``
are tagged with the ``postgres_only`` pytest marker so the SQLite
matrix lane never tries to exercise them.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0015_rls_audit_tables"
down_revision: Union[str, None] = "0014b_backfill_tenant_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES: tuple[str, ...] = (
    "customer_audit_entries",
    "webhook_events",
    "vault_audit_entries",
)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        # SQLite / others — RLS not supported; rely on app-level filter
        # plus Cerbos PDP (layers 1 and 2 of the defence chain).
        return

    for tbl in TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY {tbl}_tenant_isolation
              ON {tbl}
              USING (tenant_id = current_setting('abs.tenant_id', true))
              WITH CHECK (tenant_id = current_setting('abs.tenant_id', true));
            """
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        return

    for tbl in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
