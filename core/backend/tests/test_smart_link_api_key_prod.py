"""026 Modul E — POST /v1/smart-link/api-key with provider validation + vault store."""

from __future__ import annotations

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
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-026")


def _mock_openai_get(monkeypatch, status: int = 200):
    real = httpx.Client.get

    def _get(self, url, *args, **kwargs):
        if "api.openai.com" in str(url):
            return _FakeRsp(status, {"data": []})
        return real(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", _get)


def test_invalid_provider_returns_400(client):
    r = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "claude", "api_key": "x" * 20},
    )
    assert r.status_code == 400


def test_short_key_returns_400(client):
    r = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "openai", "api_key": "abc"},
    )
    assert r.status_code == 400


def test_invalid_provider_validation_returns_422(client, monkeypatch):
    """Provider key fails validation (mock returns 401) → 422."""
    _mock_openai_get(monkeypatch, status=401)
    r = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "openai", "api_key": "sk-bad-key-1234"},
    )
    assert r.status_code == 422
    assert "validation failed" in r.json()["detail"].lower()


def test_valid_key_stored_and_validated(client, monkeypatch):
    _mock_openai_get(monkeypatch, status=200)
    r = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "openai", "api_key": "sk-good-key-12345"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["stored"] is True
    assert body["validated"] is True
    assert body["latency_ms"] >= 0
