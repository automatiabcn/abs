"""Smart Link foundation skeleton (post-026 superset).

026 expanded the provider list (added groq + gemini) and made callback dependent
on a real OAuth token exchange — these tests assert the surface still exists.
"""

from __future__ import annotations

import httpx


def test_providers_endpoint_lists_supported_set(client):
    r = client.get("/v1/smart-link/providers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["providers"]}
    # 023 baseline + 026 expansion (groq, gemini)
    assert {"github", "openai", "anthropic", "cohere", "slack", "smtp"}.issubset(ids)
    assert {"groq", "gemini"}.issubset(ids)


def test_github_authorize_returns_url_and_state(client):
    r = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://abs.firmaadi.com/integrations"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "authorize_url" in body
    assert body["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    assert "state" in body
    assert len(body["state"]) >= 16


def test_github_callback_consumes_state_once(client, monkeypatch):
    """Even if token exchange fails (no real GitHub), state must be consumed and
    second callback must 400. Provider returns 200 with ok:false when token is
    not obtainable, which is the documented behaviour."""
    real_post = httpx.Client.post

    def _post(self, url, *args, **kwargs):
        if "github.com/login/oauth/access_token" in str(url):

            class _R:
                status_code = 200

                def json(self):
                    return {"access_token": "ghs_smoke_xyz"}

            return _R()
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)

    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://abs.firmaadi.com/r"},
    )
    state = r1.json()["state"]
    r2 = client.get(f"/v1/smart-link/github/callback?code=mockcode&state={state}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["provider"] == "github"
    assert body["code_received"] is True

    # Replay → 400
    r3 = client.get(f"/v1/smart-link/github/callback?code=mockcode&state={state}")
    assert r3.status_code == 400


def test_api_key_store_validates_provider_and_length(client, monkeypatch):
    """anthropic now requires a real provider probe; 4xx without mock,
    so we mock the validator endpoint."""
    real_post = httpx.Client.post

    class _R:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {"id": "x"}

    def _post(self, url, *args, **kwargs):
        if "api.anthropic.com" in str(url):
            return _R(400)  # bad payload but valid auth → key OK
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)

    # Unsupported provider
    r1 = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "claude", "api_key": "sk-test-12345"},
    )
    assert r1.status_code == 400
    # Too-short key
    r2 = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "openai", "api_key": "abc"},
    )
    assert r2.status_code == 400
    # Valid path
    r3 = client.post(
        "/v1/smart-link/api-key",
        json={"provider": "anthropic", "api_key": "sk-ant-mock-12345678"},
    )
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert body["ok"] is True
    assert body["stored"] is True
