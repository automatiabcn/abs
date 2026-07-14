"""feature_usage_log + meetings + meeting_segments.

Revision ID: 0004_sprint20_meetings
Revises: 0003_tenant_projects
Create Date: 2026-04-29

Adds:
  - feature_usage_log: 29-feature catalog event log (append-only).
  - meetings: WhisperX upload + status (pending|done|error) + summary.
  - meeting_segments: 1:N transcript segments with speaker tag + timing.

SQLite-compatible (no materialized views; aggregation at query time via
GROUP BY). Indexes match (tenant_slug, ts) and (meeting_id) lookup paths.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_sprint20_meetings"
down_revision: Union[str, None] = "0003_tenant_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_usage_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("feature_id", sa.String(64), nullable=False),
        sa.Column("actor_email", sa.String(254), nullable=True),
        sa.Column("ts", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_feature_usage_log_tenant_slug",
        "feature_usage_log",
        ["tenant_slug"],
    )
    op.create_index(
        "ix_feature_usage_log_feature_id",
        "feature_usage_log",
        ["feature_id"],
    )
    op.create_index(
        "ix_feature_usage_log_ts",
        "feature_usage_log",
        ["ts"],
    )

    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug", sa.String(64), nullable=False, server_default="default"
        ),
        sa.Column("uploader_email", sa.String(254), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("duration_sec", sa.Float, nullable=False, server_default="0"),
        sa.Column("speaker_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("summary", sa.String(4096), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_meetings_tenant_slug", "meetings", ["tenant_slug"])
    op.create_index("ix_meetings_uploader_email", "meetings", ["uploader_email"])
    op.create_index("ix_meetings_created_at", "meetings", ["created_at"])

    op.create_table(
        "meeting_segments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("meeting_id", sa.Integer, nullable=False),
        sa.Column("speaker_id", sa.String(32), nullable=False),
        sa.Column("start_sec", sa.Float, nullable=False),
        sa.Column("end_sec", sa.Float, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_meeting_segments_meeting_id",
        "meeting_segments",
        ["meeting_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_segments_meeting_id", table_name="meeting_segments")
    op.drop_table("meeting_segments")
    op.drop_index("ix_meetings_created_at", table_name="meetings")
    op.drop_index("ix_meetings_uploader_email", table_name="meetings")
    op.drop_index("ix_meetings_tenant_slug", table_name="meetings")
    op.drop_table("meetings")
    op.drop_index("ix_feature_usage_log_ts", table_name="feature_usage_log")
    op.drop_index("ix_feature_usage_log_feature_id", table_name="feature_usage_log")
    op.drop_index("ix_feature_usage_log_tenant_slug", table_name="feature_usage_log")
    op.drop_table("feature_usage_log")
