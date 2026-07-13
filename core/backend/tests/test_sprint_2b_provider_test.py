# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2B BUG-33 — /v1/admin/providers/{id}/test endpoint guard."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    return client.post("/v1/admin/login", json={"password": "s3cret"}).json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def test_test_endpoint_requires_admin(client):
    r = client.post("/v1/admin/providers/groq/test", json={})
    assert r.status_code == 401


def test_test_endpoint_unknown_provider_returns_404(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/openai/test",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 404


def test_test_endpoint_missing_key_returns_ok_false(client, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq/test",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "missing_api_key"
    assert body["provider"] == "groq"


def test_test_endpoint_provider_error_surfaces_ok_false(client, monkeypatch):
    """When a key is set but the provider call raises, the endpoint
    returns ``ok=false`` with the error string — never a 500."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test_dummy")
    token = _admin_token(client, monkeypatch)

    async def _fake_call_with_cascade(*args, **kwargs):
        from app.providers.schemas import ProviderError

        raise ProviderError(
            "simulated_provider_failure", provider="groq", transient=True
        )

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake_call_with_cascade
    )

    r = client.post(
        "/v1/admin/providers/groq/test",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "simulated_provider_failure" in body["error"]
