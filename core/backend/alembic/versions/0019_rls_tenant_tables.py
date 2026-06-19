"""Sprint 2L — extend Postgres RLS to the tenant-DATA tables.

Revision ID: 0019_rls_tenant_tables
Revises: 0018_project_slug_per_tenant
Create Date: 2026-06-08

Sprint 2K (0014/0015) activated RLS on the 3 audit tables as a proof of the
GUC + policy pattern. This migration extends the SAME tenant-isolation policy
to the tenant-DATA tables that are read/written strictly inside an
authenticated request, where ``app.middleware.tenant_context`` has already
pinned the ``abs.tenant_id`` GUC. A single missing application-level WHERE can
then no longer leak rows across paying tenants on the Postgres SaaS.

Policy (identical shape to 0015): a row is visible / writable only when its
tenant column equals the session GUC ``abs.tenant_id``. ENABLE + FORCE so even
the table owner is subject; ``abs_admin`` (0015b) keeps ``BYPASSRLS`` for the
operator console + cross-tenant background jobs. ``chat_messages`` has no
tenant column of its own and is scoped through its parent ``chat_sessions`` via
an EXISTS sub-select.

DELIBERATELY EXCLUDED (a strict policy here would BREAK a real flow — these
need a follow-up slice that bridges the GUC into the background/MCP paths or
runs identity reads through a BYPASSRLS connection):

  * Identity / pre-auth tables read by a GLOBAL-unique key before any tenant
    context exists — RLS would make the lookup return zero rows:
      - ``users``                 (login by globally-unique email)
      - ``failed_login_attempts`` (backoff by globally-unique email)
      - ``tenant_invites``        (claim by globally-unique magic_token_hash)
      - ``minted_token_blacklist``(MCP token revocation check by token_digest —
                                   RLS here would make a REVOKED token read as
                                   valid: a security regression)
  * Tables written from background / MCP / cascade paths that do not yet set
    the request ContextVar, so FORCE RLS WITH CHECK would reject the insert:
      - ``usage_log`` · ``feature_usage_log`` (cascade + MCP usage logging)
      - ``tenant_installed_plugins``          (sandbox runtime lookups)

(``meetings`` + ``meeting_segments`` were in this excluded set until their write
path was made multi-tenant-aware — ``api/meetings._admin_tenant`` now writes the
resolved tenant inside the authenticated upload request, where the middleware
has pinned the GUC — so they are now included above.)

SQLite (self-host + the default test lane) has no RLS engine, so
``upgrade()``/``downgrade()`` no-op there exactly like 0015.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0019_rls_tenant_tables"
down_revision: Union[str, None] = "0018_project_slug_per_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# table -> tenant column. Only tables read/written inside an authenticated
# request (GUC already pinned by the tenant-context middleware).
_DIRECT: dict[str, str] = {
    "tenants": "slug",  # the tenant's own identity row (admin context)
    "projects": "tenant_slug",
    "tenant_projects": "tenant_slug",
    "provider_keys": "tenant_slug",  # BYOK secrets — highest blast radius
    "tenant_settings": "tenant_slug",
    "project_members": "tenant_slug",
    "chat_sessions": "tenant_slug",
    # NOTE: saved_workflow is intentionally NOT here — it has no migration of its
    # own (created via SQLModel create_all on the SQLite lane only), so on a
    # Postgres alembic chain the table does not exist at this point and ALTER
    # would abort the whole migration. A future migration that CREATEs
    # saved_workflow on Postgres should add its RLS policy there (like 0020-0024).
    "meetings": "tenant_slug",  # write is multi-tenant-aware (api/meetings._admin_tenant)
}

# child table -> (parent table, child fk col, parent pk col, parent tenant col)
_CHILD: dict[str, tuple[str, str, str, str]] = {
    "chat_messages": ("chat_sessions", "session_id", "id", "tenant_slug"),
    "meeting_segments": ("meetings", "meeting_id", "id", "tenant_slug"),
}

# missing_ok=true → unset GUC yields NULL (fail-closed: NULL never matches).
_GUC = "current_setting('abs.tenant_id', true)"


def _enable(tbl: str, predicate: str) -> None:
    op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
        f"USING ({predicate}) WITH CHECK ({predicate});"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for tbl, col in _DIRECT.items():
        _enable(tbl, f"{col} = {_GUC}")
    for tbl, (ptbl, fk, ppk, pcol) in _CHILD.items():
        predicate = (
            f"EXISTS (SELECT 1 FROM {ptbl} p "
            f"WHERE p.{ppk} = {tbl}.{fk} AND p.{pcol} = {_GUC})"
        )
        _enable(tbl, predicate)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for tbl in list(_DIRECT) + list(_CHILD):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
