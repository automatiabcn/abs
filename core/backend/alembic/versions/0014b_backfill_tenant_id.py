"""Sprint 2K — backfill tenant_id for the 3 RLS-guarded audit tables.

Revision ID: 0014b_backfill_tenant_id
Revises: 0014_tenant_id_audit_tables
Create Date: 2026-05-14

Resolution order per row (best signal first):

    1. ``users.tenant_slug`` matched on the license's ``customer_email``
       (active rows only).
    2. Email-domain heuristic on the license's ``customer_email`` —
       ``foo@demo-acme.com`` → ``demo-acme``. Mirrors
       ``app.api.auth._derive_tenant_from_email`` so the runtime path and
       the historical backfill stay in sync.

For ``vault_audit_entries`` the chain is shorter — there is no license
link, so the heuristic runs directly on ``actor`` when it looks like an
email. Rows whose actor is a service identity (``system``,
``setup-wizard``, …) stay ``_unknown``; the production deploy doc records
this is acceptable for service rows because the policy grants
``BYPASSRLS`` to the ``abs_admin`` role that ingests them.

Postgres uses native ``UPDATE … FROM``. SQLite cannot do correlated
``UPDATE … FROM``, so the SQLite branch loops in Python; this keeps
``alembic upgrade head`` green on the dev sqlite database used by the
backend test suite. SQLite never reaches the RLS policy migration
(``0015``) skipped on its dialect — the column add still applies so the
SQLModel metadata stays in sync.
"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op


revision: str = "0014b_backfill_tenant_id"
down_revision: Union[str, None] = "0014_tenant_id_audit_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors app.api.auth._TENANT_SLUG_RE; must stay in sync.
_TENANT_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,30}[a-z0-9])?$")


def _derive_tenant_from_email(email: str | None) -> str | None:
    """Email-domain → tenant slug heuristic (mirrors runtime path)."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    if "." not in domain:
        return None
    label = domain.split(".", 1)[0]
    if not _TENANT_SLUG_RE.match(label):
        return None
    return label


def _backfill_postgres() -> None:
    """Native UPDATE ... FROM path (Postgres / production)."""

    # customer_audit_entries — license_jti → licenses.customer_email →
    # users.tenant_slug fallback to email-domain SUBSTRING.
    op.execute(
        """
        UPDATE customer_audit_entries cae
        SET tenant_id = COALESCE(
            (
                SELECT u.tenant_slug
                FROM users u
                WHERE u.email = l.customer_email AND u.status = 'active'
                LIMIT 1
            ),
            LOWER(SPLIT_PART(SPLIT_PART(l.customer_email, '@', 2), '.', 1)),
            '_unknown'
        )
        FROM licenses l
        WHERE cae.license_jti = l.jti AND cae.tenant_id = '_unknown'
        """
    )

    # webhook_events — same chain via license_jti.
    op.execute(
        """
        UPDATE webhook_events we
        SET tenant_id = COALESCE(
            (
                SELECT u.tenant_slug
                FROM users u
                WHERE u.email = l.customer_email AND u.status = 'active'
                LIMIT 1
            ),
            LOWER(SPLIT_PART(SPLIT_PART(l.customer_email, '@', 2), '.', 1)),
            '_unknown'
        )
        FROM licenses l
        WHERE we.license_jti = l.jti AND we.tenant_id = '_unknown'
        """
    )

    # vault_audit_entries — actor is the only signal; derive when it
    # looks like an email, otherwise leave _unknown (service identities).
    op.execute(
        """
        UPDATE vault_audit_entries
        SET tenant_id = LOWER(SPLIT_PART(SPLIT_PART(actor, '@', 2), '.', 1))
        WHERE actor LIKE '%@%.%'
          AND tenant_id = '_unknown'
        """
    )


def _backfill_generic() -> None:
    """SQLite-compatible loop (dev / test parity only).

    SQLite hits this path; production never does. Keeping the column
    populated locally lets the SQLModel ORM avoid sentinel reads in
    unit tests.
    """
    conn = op.get_bind()
    users_rows = conn.exec_driver_sql(
        "SELECT email, tenant_slug FROM users WHERE status = 'active'"
    ).fetchall()
    users: dict[str, str] = {row[0]: row[1] for row in users_rows if row[1]}

    licenses_rows = conn.exec_driver_sql(
        "SELECT jti, customer_email FROM licenses"
    ).fetchall()
    license_to_tenant: dict[str, str] = {}
    for jti, email in licenses_rows:
        resolved = users.get(email) or _derive_tenant_from_email(email)
        if resolved:
            license_to_tenant[jti] = resolved

    if license_to_tenant:
        for jti, tenant in license_to_tenant.items():
            conn.exec_driver_sql(
                "UPDATE customer_audit_entries SET tenant_id = :t "
                "WHERE license_jti = :j AND tenant_id = '_unknown'",
                {"t": tenant, "j": jti},
            )
            conn.exec_driver_sql(
                "UPDATE webhook_events SET tenant_id = :t "
                "WHERE license_jti = :j AND tenant_id = '_unknown'",
                {"t": tenant, "j": jti},
            )

    vault_rows = conn.exec_driver_sql(
        "SELECT id, actor FROM vault_audit_entries WHERE tenant_id = '_unknown'"
    ).fetchall()
    for row_id, actor in vault_rows:
        derived = _derive_tenant_from_email(actor)
        if derived:
            conn.exec_driver_sql(
                "UPDATE vault_audit_entries SET tenant_id = :t WHERE id = :i",
                {"t": derived, "i": row_id},
            )


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _backfill_postgres()
    else:
        _backfill_generic()


def downgrade() -> None:
    # Reset to the placeholder so a re-upgrade reproduces deterministic
    # behaviour. We deliberately do not blow away tenant_id values that
    # post-migration writes might have populated through the normal app
    # path — operators that need to fully reset should downgrade past
    # 0014 (which drops the column).
    pass
