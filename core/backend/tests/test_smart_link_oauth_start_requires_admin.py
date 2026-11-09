"""Beginning an OAuth connection is an admin's act.

The authorize routes mint the state that the callback trusts. Whoever holds a
state can finish the handshake, and the token that comes back is stored as this
server's credential for that provider. Both routes answered anyone.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import OAuthState
from app.db.session import get_engine


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-oauth-start")


def _states() -> int:
    with Session(get_engine()) as db:
        return len(db.scalars(select(OAuthState)).all())


def _start(client, provider: str, headers: dict | None = None):
    if provider == "github":
        return client.post(
            "/v1/smart-link/github/authorize",
            json={"redirect_url": "https://abs.corp.example/integrations"},
            headers=headers or {},
        )
    return client.get("/v1/smart-link/slack/authorize", headers=headers or {})


@pytest.mark.parametrize("provider", ["github", "slack"])
def test_a_stranger_cannot_start_a_connection(client, provider):
    before = _states()

    resp = _start(client, provider)

    assert resp.status_code == 401, resp.text
    assert "state" not in resp.text
    assert _states() == before, "a state row was minted for an anonymous caller"


@pytest.mark.parametrize("provider", ["github", "slack"])
def test_a_wrong_token_cannot_start_a_connection(client, provider):
    before = _states()

    resp = _start(client, provider, {"Authorization": "Bearer not-the-admin"})

    assert resp.status_code == 403, resp.text
    assert _states() == before


@pytest.mark.parametrize("provider", ["github", "slack"])
def test_the_admin_still_can(client, provider):
    resp = _start(client, provider, {"Authorization": "Bearer test-admin-oauth-start"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"]
