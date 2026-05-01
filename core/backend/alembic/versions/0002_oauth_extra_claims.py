"""T-005 — Add extra_claims_json to oauth_auth_codes and oauth_refresh_tokens.

Carries tenant_id / roles / future custom claims into issued JWTs.

Revision ID: 0002_oauth_extra_claims
Revises: 0001_oauth_baseline
Create Date: 2026-04-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_oauth_extra_claims"
down_revision: Union[str, None] = "0001_oauth_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("oauth_auth_codes") as batch:
        batch.add_column(
            sa.Column(
                "extra_claims_json",
                sa.String(2048),
                nullable=False,
                server_default="{}",
            )
        )
    with op.batch_alter_table("oauth_refresh_tokens") as batch:
        batch.add_column(
            sa.Column(
                "extra_claims_json",
                sa.String(2048),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("oauth_refresh_tokens") as batch:
        batch.drop_column("extra_claims_json")
    with op.batch_alter_table("oauth_auth_codes") as batch:
        batch.drop_column("extra_claims_json")
