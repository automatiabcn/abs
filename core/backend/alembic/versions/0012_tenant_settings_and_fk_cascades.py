"""Sprint 2C - tenant branding columns + FK CASCADE follow-up (Lesson 9).

Revision ID: 0012_tenant_settings_fk
Revises: 0011_tenant_installed_plugins
Create Date: 2026-05-10

Two related changes packaged into a single migration:

1. ``tenants`` gains ``branding_message`` (max 500), ``logo_url``
   (max 512), ``primary_color`` (#RRGGBB, max 7). All nullable so the
   ALTER is non-blocking on existing rows.
2. ``tenant_invites.tenant_id`` and ``tenant_installed_plugins.tenant_id``
   gain a foreign key to ``tenants.slug`` with ``ondelete=CASCADE`` -
   the Lesson 9 follow-up the Sprint 2B notes deferred. Pre-step seeds
   ``default`` plus any orphan ``tenant_id`` value the existing rows
   already reference, otherwise the ALTER would fail on Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError


revision: str = "0012_tenant_settings_fk"
down_revision: Union[str, None] = "0011_tenant_installed_plugins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_tenant_rows() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    exists = bind.execute(
        sa.text("SELECT 1 FROM tenants WHERE slug = :s"),
        {"s": "default"},
    ).first()
    if exists is None:
        bind.execute(
            sa.text(
                "INSERT INTO tenants(slug, name, created_at) "
                "VALUES (:s, :n, :c)"
            ),
            {"s": "default", "n": "default", "c": now},
        )

    for table in ("tenant_invites", "tenant_installed_plugins"):
        try:
            rows = bind.execute(
                sa.text(
                    f"SELECT DISTINCT tenant_id FROM {table} "
                    f"WHERE tenant_id NOT IN (SELECT slug FROM tenants)"
                )
            ).fetchall()
        except OperationalError:
            continue
        for row in rows:
            slug = row[0]
            if not slug:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO tenants(slug, name, created_at) "
                    "VALUES (:s, :n, :c)"
                ),
                {"s": slug, "n": slug, "c": now},
            )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("tenants") as batch:
        batch.add_column(
            sa.Column("branding_message", sa.String(500), nullable=True)
        )
        batch.add_column(sa.Column("logo_url", sa.String(512), nullable=True))
        batch.add_column(sa.Column("primary_color", sa.String(7), nullable=True))

    _seed_tenant_rows()

    if dialect == "sqlite":
        with op.batch_alter_table("tenant_invites") as batch:
            batch.create_foreign_key(
                "fk_tenant_invites_tenant_id",
                referent_table="tenants",
                local_cols=["tenant_id"],
                remote_cols=["slug"],
                ondelete="CASCADE",
            )
        with op.batch_alter_table("tenant_installed_plugins") as batch:
            batch.create_foreign_key(
                "fk_tenant_installed_plugins_tenant_id",
                referent_table="tenants",
                local_cols=["tenant_id"],
                remote_cols=["slug"],
                ondelete="CASCADE",
            )
    else:
        op.create_foreign_key(
            "fk_tenant_invites_tenant_id",
            "tenant_invites",
            "tenants",
            ["tenant_id"],
            ["slug"],
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            "fk_tenant_installed_plugins_tenant_id",
            "tenant_installed_plugins",
            "tenants",
            ["tenant_id"],
            ["slug"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("tenant_installed_plugins") as batch:
            batch.drop_constraint(
                "fk_tenant_installed_plugins_tenant_id", type_="foreignkey"
            )
        with op.batch_alter_table("tenant_invites") as batch:
            batch.drop_constraint(
                "fk_tenant_invites_tenant_id", type_="foreignkey"
            )
    else:
        op.drop_constraint(
            "fk_tenant_installed_plugins_tenant_id",
            "tenant_installed_plugins",
            type_="foreignkey",
        )
        op.drop_constraint(
            "fk_tenant_invites_tenant_id",
            "tenant_invites",
            type_="foreignkey",
        )

    with op.batch_alter_table("tenants") as batch:
        batch.drop_column("primary_color")
        batch.drop_column("logo_url")
        batch.drop_column("branding_message")
