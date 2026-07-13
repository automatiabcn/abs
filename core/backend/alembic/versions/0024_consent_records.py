"""Consent Ledger — consent_records table (+ RLS).

Revision ID: 0024_consent_records
Revises: 0023_workflow_runs
Create Date: 2026-06-08

Per-contact, per-channel consent + legal basis. Tenant-scoped; RLS like
0019-0023.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024_consent_records"
down_revision: Union[str, None] = "0023_workflow_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUC = "current_setting('abs.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("contact_email", sa.String(254), nullable=False),
        sa.Column(
            "email_consent", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "phone_consent", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("sms_consent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "whatsapp_consent", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("do_not_call", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("opt_in_source", sa.String(64), nullable=False, server_default=""),
        sa.Column("opt_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opt_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_basis", sa.String(48), nullable=False, server_default=""),
        sa.Column(
            "consent_evidence", sa.String(512), nullable=False, server_default=""
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_consent_records_tenant_slug", "consent_records", ["tenant_slug"]
    )
    op.create_index(
        "ix_consent_records_contact_email", "consent_records", ["contact_email"]
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE consent_records FORCE ROW LEVEL SECURITY;")
        op.execute(
            "CREATE POLICY consent_records_tenant_isolation ON consent_records "
            f"USING (tenant_slug = {_GUC}) WITH CHECK (tenant_slug = {_GUC});"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS consent_records_tenant_isolation ON consent_records;"
        )
        op.execute("ALTER TABLE consent_records NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE consent_records DISABLE ROW LEVEL SECURITY;")
    op.drop_table("consent_records")
