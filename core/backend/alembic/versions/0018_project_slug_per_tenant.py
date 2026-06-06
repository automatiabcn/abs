"""Project slug unique PER TENANT (was globally unique).

Revision ID: 0018_project_slug_per_tenant
Revises: 0017_tenant_settings
Create Date: 2026-06-06

0003 made projects.slug globally unique (column UNIQUE + a unique index), so
tenant A's "default"/"research" slug would block tenant B. Switch to a
composite unique (tenant_slug, slug). SQLite deployments use create_all (model)
and skip alembic; this migration runs on Postgres + the SQLite round-trip test,
so it is dialect-aware.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0018_project_slug_per_tenant"
down_revision: Union[str, None] = "0017_tenant_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    # slug index: unique -> plain (lookups still indexed)
    op.drop_index("ix_projects_slug", table_name="projects")
    op.create_index("ix_projects_slug", "projects", ["slug"])
    if is_pg:
        # drop the column-level global unique (auto-named projects_slug_key)
        op.drop_constraint("projects_slug_key", "projects", type_="unique")
        op.create_unique_constraint(
            "uq_project_tenant_slug", "projects", ["tenant_slug", "slug"]
        )
    else:
        # SQLite: add the composite unique via batch (column-level anonymous
        # unique can't be dropped by name; fresh SQLite uses create_all/model
        # which already omits it — this path only runs in the round-trip test).
        with op.batch_alter_table("projects") as batch:
            batch.create_unique_constraint(
                "uq_project_tenant_slug", ["tenant_slug", "slug"]
            )


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    if is_pg:
        op.drop_constraint("uq_project_tenant_slug", "projects", type_="unique")
        op.create_unique_constraint("projects_slug_key", "projects", ["slug"])
    else:
        with op.batch_alter_table("projects") as batch:
            batch.drop_constraint("uq_project_tenant_slug", type_="unique")
    op.drop_index("ix_projects_slug", table_name="projects")
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)
