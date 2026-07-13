"""Q12 / Brief 3 R4 — chat session threading metadata.

Revision ID: 0009_chat_threading
Revises: 0008_minted_token_blacklist
Create Date: 2026-05-07

Adds four columns to ``chat_sessions`` so the panel sidebar can render
pin / archive / search / sort UI without extra round-trips:

    pinned             BOOLEAN  DEFAULT 0  NOT NULL
    archived_at        DATETIME NULL
    last_activity_at   DATETIME NOT NULL  -- backfilled from updated_at
    message_count      INTEGER  DEFAULT 0 NOT NULL  -- backfilled by COUNT()

`last_activity_at` is denormalised from `chat_messages.created_at` so the
sidebar can sort without a JOIN; the chat handler updates it whenever a
new message lands. `message_count` is a counter cache for the same
reason.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_chat_threading"
down_revision: Union[str, None] = "0008_minted_token_blacklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(
            sa.Column(
                "pinned",
                sa.Boolean,
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("archived_at", sa.DateTime, nullable=True))
        batch.add_column(
            sa.Column(
                "last_activity_at",
                sa.DateTime,
                nullable=True,  # set NOT NULL after backfill
            )
        )
        batch.add_column(
            sa.Column(
                "message_count",
                sa.Integer,
                nullable=False,
                server_default="0",
            )
        )

    # Backfill last_activity_at from updated_at (existing rows).
    op.execute(
        "UPDATE chat_sessions SET last_activity_at = updated_at "
        "WHERE last_activity_at IS NULL"
    )

    # Backfill message_count from chat_messages (counter cache).
    op.execute(
        "UPDATE chat_sessions SET message_count = ("
        "SELECT COUNT(*) FROM chat_messages "
        "WHERE chat_messages.session_id = chat_sessions.id)"
    )

    # Now flip last_activity_at to NOT NULL — every row has a value.
    with op.batch_alter_table("chat_sessions") as batch:
        batch.alter_column(
            "last_activity_at",
            existing_type=sa.DateTime,
            nullable=False,
        )

    op.create_index(
        "ix_chat_sessions_last_activity_at",
        "chat_sessions",
        ["last_activity_at"],
    )
    op.create_index(
        "ix_chat_sessions_archived_at",
        "chat_sessions",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_archived_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_last_activity_at", table_name="chat_sessions")
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_column("message_count")
        batch.drop_column("last_activity_at")
        batch.drop_column("archived_at")
        batch.drop_column("pinned")
