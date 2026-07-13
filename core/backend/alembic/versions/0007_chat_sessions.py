"""Q8 / Phase A — chat_sessions + chat_messages tables.

Revision ID: 0007_chat_sessions
Revises: 0006_users_magic_link
Create Date: 2026-05-01

Adds the two tables that back `/v1/chat/*` (sessions list + per-message
streaming history). Both are tenant-scoped via `tenant_slug`; cross-tenant
reads are gated at the API layer (see app/api/chat.py).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_chat_sessions"
down_revision: Union[str, None] = "0006_users_magic_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_slug",
            sa.String(64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("user_email", sa.String(254), nullable=False),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            server_default="Yeni sohbet",
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_chat_sessions_tenant_slug", "chat_sessions", ["tenant_slug"])
    op.create_index("ix_chat_sessions_user_email", "chat_sessions", ["user_email"])
    op.create_index("ix_chat_sessions_created_at", "chat_sessions", ["created_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.String(16384), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("tool_calls", sa.String(8192), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_sessions_created_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_email", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_tenant_slug", table_name="chat_sessions")
    op.drop_table("chat_sessions")
