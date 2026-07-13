"""meetings.audio_sha256 + meetings.quality_note — recognise a recording we
already have, and mark one that holds no speech.

Revision ID: 0028_meeting_audio_fingerprint
Revises: 0027_minted_token_record
Create Date: 2026-07-13

The fingerprint is over the audio bytes, not the filename, so the same
recording arriving under a second name is still one meeting — otherwise every
retried upload pays for transcription again and puts a second copy of every
passage in the vector store, where duplicate hits read as independent sources
agreeing with each other.

Both columns are nullable-with-default rather than backfilled: existing rows
have no fingerprint and never will (the audio is long gone), and an empty
fingerprint deliberately matches nothing, so old meetings simply never
participate in dedup instead of colliding with each other on "".
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028_meeting_audio_fingerprint"
down_revision: Union[str, None] = "0027_minted_token_record"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("audio_sha256", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "meetings",
        sa.Column("quality_note", sa.String(512), nullable=False, server_default=""),
    )
    # Not unique: two tenants may legitimately hold the same recording, and the
    # lookup is always scoped by tenant_slug.
    op.create_index("ix_meetings_audio_sha256", "meetings", ["audio_sha256"])


def downgrade() -> None:
    op.drop_index("ix_meetings_audio_sha256", table_name="meetings")
    op.drop_column("meetings", "quality_note")
    op.drop_column("meetings", "audio_sha256")
