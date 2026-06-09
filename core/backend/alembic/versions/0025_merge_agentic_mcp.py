"""Merge the agentic-tables branch (0024) and the external-mcp branch (0020).

Revision ID: 0025_merge_agentic_mcp
Revises: 0024_consent_records, 0020_external_mcp
Create Date: 2026-06-09

Both branches forked from 0019_rls_tenant_tables and shipped independently; this
merge gives the chain a single head again. No schema change.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0025_merge_agentic_mcp"
down_revision: Union[str, Sequence[str], None] = ("0024_consent_records", "0020_external_mcp")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
