"""POST /v1/smart-link/api-key is an admin write.

It was the only route in the router that changed the connected-secret store
without asking who was calling. These tests pin the gate: no token and a wrong
token are refused before anything is validated or written.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import ConnectedSecret
from app.db.session import get_engine

_BODY = {"provider": "smtp", "api_key": "planted-by-a-stranger"}


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-gate")


def _stored(key_name: str) -> list[ConnectedSecret]:
    with Session(get_engine()) as db:
        return list(
            db.scalars(
                select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
            ).all()
        )


def test_anonymous_caller_is_refused_and_nothing_is_written(client):
    r = client.post("/v1/smart-link/api-key", json=_BODY)
    assert r.status_code == 401, r.text
    assert _stored("smtp_api_key") == []


def test_wrong_token_is_refused_and_nothing_is_written(client):
    r = client.post(
        "/v1/smart-link/api-key",
        json=_BODY,
        headers={"Authorization": "Bearer not-the-admin-token"},
    )
    assert r.status_code == 403, r.text
    assert _stored("smtp_api_key") == []


def test_anonymous_caller_cannot_overwrite_an_existing_secret(client):
    admin = {"Authorization": "Bearer test-admin-gate"}
    first = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "smtp", "api_key": "the-operators-value"},
        headers=admin,
    )
    assert first.status_code == 200, first.text
    before = _stored("smtp_api_key")[0].encrypted_value

    r = client.post("/v1/smart-link/api-key", json=_BODY)
    assert r.status_code == 401, r.text
    assert _stored("smtp_api_key")[0].encrypted_value == before


def test_the_gate_runs_before_the_provider_is_called(client, monkeypatch):
    """An anonymous request must not make the server validate a key upstream."""
    called = []
    monkeypatch.setattr(
        "app.api.smart_link.validate_provider",
        lambda provider, key: called.append(provider) or {"ok": True, "latency_ms": 1},
    )
    r = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "openai", "api_key": "sk-anonymous-probe-123"},
    )
    assert r.status_code == 401, r.text
    assert called == []
