"""Growth domain — companies / contacts / leads / opportunities (+ RLS).

Revision ID: 0021_growth_domain
Revises: 0020_agentic_tables
Create Date: 2026-06-08

The SQL home for the Growth Context Graph entities. Tenant-scoped; RLS-enrolled
like 0019/0020. SQLite (tests + self-host) creates them via create_all and the
RLS steps no-op there.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0021_growth_domain"
down_revision: Union[str, None] = "0020_agentic_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"
_RLS_TABLES = ("companies", "contacts", "leads", "opportunities")


def _enable_rls(tbl: str) -> None:
    op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
        f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
    )


def _ts() -> sa.Column:
    return sa.Column(
        "tenant_slug", sa.String(64), nullable=False, server_default="default"
    )


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True),
        _ts(),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("vkn", sa.String(32), nullable=True),
        sa.Column("domain", sa.String(128), nullable=True),
        sa.Column("sector", sa.String(96), nullable=False, server_default=""),
        sa.Column("location", sa.String(128), nullable=False, server_default=""),
        sa.Column("size", sa.String(32), nullable=False, server_default=""),
        sa.Column("source", sa.String(64), nullable=False, server_default=""),
        sa.Column("lifecycle", sa.String(24), nullable=False, server_default="lead"),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("canonical", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("merged_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("match_confidence", sa.Float, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_tenant_slug", "companies", ["tenant_slug"])
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_vkn", "companies", ["vkn"])
    op.create_index("ix_companies_domain", "companies", ["domain"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        _ts(),
        sa.Column("company_id", sa.Integer, nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(48), nullable=True),
        sa.Column("role", sa.String(96), nullable=False, server_default=""),
        sa.Column("consent_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contacts_tenant_slug", "contacts", ["tenant_slug"])
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        _ts(),
        sa.Column("company_id", sa.Integer, nullable=True),
        sa.Column("source", sa.String(64), nullable=False, server_default=""),
        sa.Column("intent", sa.String(24), nullable=False, server_default="watching"),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("score_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("evidence_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(24), nullable=False, server_default="new"),
        sa.Column("owner", sa.String(254), nullable=False, server_default=""),
        sa.Column("consent_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leads_tenant_slug", "leads", ["tenant_slug"])
    op.create_index("ix_leads_company_id", "leads", ["company_id"])
    op.create_index("ix_leads_score", "leads", ["score"])
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer, primary_key=True),
        _ts(),
        sa.Column("company_id", sa.Integer, nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="lead"),
        sa.Column("amount", sa.Float, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="TRY"),
        sa.Column("campaign", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunities_tenant_slug", "opportunities", ["tenant_slug"])
    op.create_index("ix_opportunities_company_id", "opportunities", ["company_id"])
    op.create_index("ix_opportunities_stage", "opportunities", ["stage"])

    if op.get_bind().dialect.name == "postgresql":
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for tbl in _RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
    for tbl in ("opportunities", "leads", "contacts", "companies"):
        op.drop_table(tbl)
