"""026 Modul A — GitHub OAuth production: state DB cache, code exchange, refresh, revoke."""

from __future__ import annotations

import time

import httpx
import pytest

from app.config import settings


class _FakeRsp:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-026")


def _mock_token_post(monkeypatch, token: str):
    """Patch only GitHub OAuth endpoint; everything else falls through to the
    real httpx.Client.post (which TestClient also uses via ASGITransport)."""
    real_post = httpx.Client.post

    def _post(self, url, *args, **kwargs):
        url_str = str(url)
        if "github.com" in url_str and "access_token" in url_str:
            return _FakeRsp(
                200,
                {
                    "access_token": token,
                    "scope": "repo,read:user",
                    "token_type": "bearer",
                },
            )
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)


def test_authorize_state_persisted_then_callback_succeeds(client, monkeypatch):
    _mock_token_post(monkeypatch, "ghs_mock_token_xyz")
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://abs.firmaadi.com/connect"},
    )
    assert r1.status_code == 200
    state = r1.json()["state"]
    assert "github.com/login/oauth/authorize" in r1.json()["authorize_url"]

    r2 = client.get(f"/v1/smart-link/github/callback?code=mock&state={state}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True
    assert body["token_stored_via_vault"] is True


def test_callback_state_replay_blocked(client, monkeypatch):
    _mock_token_post(monkeypatch, "ghs_mock_token_replay")
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://x"},
    )
    state = r1.json()["state"]
    r2 = client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    assert r2.status_code == 200
    r3 = client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    assert r3.status_code == 400


def test_callback_invalid_state_rejected(client):
    r = client.get("/v1/smart-link/github/callback?code=x&state=does-not-exist")
    assert r.status_code == 400


def test_refresh_requires_admin_and_rotates(client, monkeypatch):
    _mock_token_post(monkeypatch, "ghs_initial_for_refresh")
    # Connect first
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://x"},
    )
    state = r1.json()["state"]
    client.get(f"/v1/smart-link/github/callback?code=x&state={state}")

    # No auth
    r2 = client.post("/v1/smart-link/github/refresh")
    assert r2.status_code == 401
    # Wrong token
    r3 = client.post(
        "/v1/smart-link/github/refresh",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r3.status_code == 403
    # Valid token
    r4 = client.post(
        "/v1/smart-link/github/refresh",
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r4.status_code == 200
    assert r4.json()["rotated"] is True


def test_revoke_clears_token(client, monkeypatch):
    _mock_token_post(monkeypatch, "ghs_to_revoke")
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://x"},
    )
    state = r1.json()["state"]
    client.get(f"/v1/smart-link/github/callback?code=x&state={state}")

    r2 = client.delete(
        "/v1/smart-link/github",
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
