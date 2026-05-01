"""026 Modul B — Slack OAuth + channel post."""

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


def _patch_slack(monkeypatch, *, oauth_ok=True, post_ok=True, bot_token="xoxb-mock-token"):
    real_post = httpx.Client.post

    def _post(self, url, *args, **kwargs):
        url_str = str(url)
        if "slack.com/api/oauth.v2.access" in url_str:
            if oauth_ok:
                return _FakeRsp(200, {"ok": True, "access_token": bot_token, "team": {"id": "T1"}})
            return _FakeRsp(200, {"ok": False, "error": "invalid_code"})
        if "slack.com/api/chat.postMessage" in url_str:
            if post_ok:
                return _FakeRsp(200, {"ok": True, "ts": "1234.5678"})
            return _FakeRsp(200, {"ok": False, "error": "channel_not_found"})
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)


def test_slack_authorize_returns_state_and_url(client):
    r = client.get("/v1/smart-link/slack/authorize")
    assert r.status_code == 200
    body = r.json()
    assert body["authorize_url"].startswith("https://slack.com/oauth/v2/authorize")
    assert "state" in body and len(body["state"]) >= 16


def test_slack_callback_stores_bot_token(client, monkeypatch):
    _patch_slack(monkeypatch, oauth_ok=True)
    r1 = client.get("/v1/smart-link/slack/authorize")
    state = r1.json()["state"]
    r2 = client.get(f"/v1/smart-link/slack/callback?code=mock&state={state}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True
    assert body["token_stored_via_vault"] is True


def test_slack_post_requires_admin(client):
    r = client.post(
        "/v1/smart-link/slack/post",
        json={"channel": "#general", "text": "hi"},
    )
    assert r.status_code == 401


def test_slack_post_with_admin_after_connect(client, monkeypatch):
    _patch_slack(monkeypatch, oauth_ok=True, post_ok=True)
    r1 = client.get("/v1/smart-link/slack/authorize")
    state = r1.json()["state"]
    client.get(f"/v1/smart-link/slack/callback?code=mock&state={state}")

    r = client.post(
        "/v1/smart-link/slack/post",
        json={"channel": "#general", "text": "ABS connected"},
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "ts" in body
