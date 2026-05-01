"""T-009 — Tenant + project + tenant_projects (M2M).

Revision ID: 0003_tenant_projects
Revises: 0002_oauth_extra_claims
Create Date: 2026-04-28

Adds:
  - tenants(id, slug, name, created_at) — `slug` is the JWT `tnt` claim value.
  - projects(id, tenant_id, name, owner_subject, qdrant_collection, created_at).
  - tenant_projects(tenant_id, project_id, role, granted_at) — M2M for cross-tenant
    project sharing (e.g. parent tenants viewing child workspace artefacts).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tenant_projects"
down_revision: Union[str, None] = "0002_oauth_extra_claims"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("archived_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(96), nullable=False, unique=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("owner_subject", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "qdrant_collection",
            sa.String(128),
            nullable=False,
            server_default="abs_documents",
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("archived_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)
    op.create_index("ix_projects_tenant_slug", "projects", ["tenant_slug"])

    op.create_table(
        "tenant_projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_slug", sa.String(64), nullable=False),
        sa.Column("project_slug", sa.String(96), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("granted_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_tenant_projects_unique",
        "tenant_projects",
        ["tenant_slug", "project_slug"],
        unique=True,
    )
    op.create_index(
        "ix_tenant_projects_tenant", "tenant_projects", ["tenant_slug"]
    )
    op.create_index(
        "ix_tenant_projects_project", "tenant_projects", ["project_slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_projects_project", "tenant_projects")
    op.drop_index("ix_tenant_projects_tenant", "tenant_projects")
    op.drop_index("ix_tenant_projects_unique", "tenant_projects")
    op.drop_table("tenant_projects")

    op.drop_index("ix_projects_tenant_slug", "projects")
    op.drop_index("ix_projects_slug", "projects")
    op.drop_table("projects")

    op.drop_index("ix_tenants_slug", "tenants")
    op.drop_table("tenants")
