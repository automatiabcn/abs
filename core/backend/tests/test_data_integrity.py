"""Q11 Round 5 / L14 — data integrity regression coverage.

Two contracts under test:

  1. The Alembic migration chain reaches `0008_minted_token_blacklist`
     and the table physically exists on disk after `alembic upgrade
     head`. Q11-L14-001 exists because Q10 Round 14 shipped the model
     without the matching migration; this test would have caught it
     at the time.

  2. A revoked token's row survives a fresh DB connection — i.e. the
     revoke endpoint's INSERT actually commits, and a subsequent
     verify_token() call from a brand-new Session still sees the
     digest in the blacklist.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlmodel import Session, select

from app.api.mcp_tokens import _token_digest
from app.db.models import MintedTokenBlacklist
from app.db.session import get_engine


class TestQ11L14AlembicChain:
    def test_minted_token_blacklist_migration_in_chain(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config("alembic.ini")
        scripts = ScriptDirectory.from_config(cfg)
        revs = {sc.revision: sc for sc in scripts.walk_revisions()}
        assert "0008_minted_token_blacklist" in revs, (
            "Q11-L14-001: migration 0008_minted_token_blacklist missing "
            "from Alembic chain — Q10 Round 14 shipped the SQLModel but "
            "skipped this revision."
        )
        sc = revs["0008_minted_token_blacklist"]
        assert sc.down_revision == "0007_chat_sessions", (
            f"0008 should chain after 0007_chat_sessions, "
            f"got down_revision={sc.down_revision}"
        )

    def test_minted_token_blacklist_table_on_disk(self):
        inspector = inspect(get_engine())
        assert "minted_token_blacklist" in inspector.get_table_names()

        cols = {c["name"] for c in inspector.get_columns("minted_token_blacklist")}
        expected = {
            "id",
            "token_digest",
            "tenant_slug",
            "label",
            "revoked_by",
            "revoked_at",
            "expires_at",
            "reason",
        }
        missing = expected - cols
        assert not missing, f"missing columns: {missing}"


class TestQ11L14RevokePersistence:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200
        return client

    def test_revoke_writes_row_visible_from_fresh_session(self, admin_client):
        r = admin_client.post(
            "/v1/mcp/tokens",
            json={"label": "probe", "scope": "all", "ttl_days": 1},
        )
        assert r.status_code == 201
        token = r.json()["token"]

        rev = admin_client.post(
            "/v1/mcp/tokens/revoke",
            json={"token": token, "reason": "q11 integrity"},
        )
        assert rev.status_code == 204

        digest = _token_digest(token)
        with Session(get_engine()) as db:
            row = db.exec(
                select(MintedTokenBlacklist).where(
                    MintedTokenBlacklist.token_digest == digest
                )
            ).first()
        assert row is not None, (
            "revoked token digest not persisted — Q10-L6-002 INSERT "
            "may have rolled back."
        )
        assert row.label == "probe"
        assert row.reason == "q11 integrity"

    def test_revoked_token_replay_rejected(self, admin_client):
        r = admin_client.post(
            "/v1/mcp/tokens",
            json={"label": "q11-replay", "scope": "all", "ttl_days": 1},
        )
        token = r.json()["token"]

        admin_client.post("/v1/mcp/tokens/revoke", json={"token": token})

        replay = admin_client.get(
            "/v1/mcp/tokens/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert replay.status_code == 401
        assert replay.json()["detail"] == "token_revoked"
