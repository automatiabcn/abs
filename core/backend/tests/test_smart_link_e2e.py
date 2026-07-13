"""024 Modul E — Smart Link OAuth + API key end-to-end (post-026 superset)."""

from __future__ import annotations

import httpx


def test_e2e_github_oauth_full_round_trip(client, monkeypatch):
    """authorize → state issued → callback with state succeeds.

    026 added real OAuth token exchange — mock the GitHub endpoint.
    """
    real_post = httpx.Client.post

    def _post(self, url, *args, **kwargs):
        if "github.com/login/oauth/access_token" in str(url):

            class _R:
                status_code = 200

                def json(self):
                    return {"access_token": "ghs_e2e_token"}

            return _R()
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)

    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://abs.firmaadi.com/integrations"},
    )
    assert r1.status_code == 200
    body = r1.json()
    state = body["state"]
    assert body["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    assert "state=" + state in body["authorize_url"]

    r2 = client.get(f"/v1/smart-link/github/callback?code=abc123&state={state}")
    assert r2.status_code == 200
    cb = r2.json()
    assert cb["ok"] is True
    assert cb["provider"] == "github"
    assert cb["code_received"] is True
    assert cb["redirect_url"] == "https://abs.firmaadi.com/integrations"


def test_e2e_callback_replay_blocked(client):
    """Used state cannot be replayed (one-time)."""
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://abs.firmaadi.com/cb"},
    )
    state = r1.json()["state"]
    r2 = client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    assert r2.status_code == 200
    r3 = client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    assert r3.status_code == 400


def test_e2e_api_key_store_for_each_provider(client, monkeypatch):
    """All non-OAuth providers accept API key storage (with mock validators)."""
    real_get = httpx.Client.get
    real_post = httpx.Client.post

    class _R200:
        status_code = 200

        def json(self):
            return {"data": []}

    class _R400:
        status_code = 400

        def json(self):
            return {"error": "bad"}

    def _get(self, url, *args, **kwargs):
        u = str(url)
        if (
            "openai.com" in u
            or "cohere.ai" in u
            or "groq.com" in u
            or "googleapis" in u
        ):
            return _R200()
        return real_get(self, url, *args, **kwargs)

    def _post(self, url, *args, **kwargs):
        if "anthropic.com" in str(url):
            return _R400()  # 400 = key valid, payload bad
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", _get)
    monkeypatch.setattr(httpx.Client, "post", _post)

    for provider in ("openai", "anthropic", "cohere", "smtp"):
        r = client.post(
            "/v1/smart-link/api-key",
            json={"provider": provider, "api_key": "mock-1234567890abcdef"},
        )
        assert r.status_code == 200, f"{provider} failed: {r.text}"
        body = r.json()
        assert body["ok"] is True
        assert body["provider"] == provider
        assert body["stored"] is True


def test_e2e_providers_endpoint_lists_all_six(client):
    r = client.get("/v1/smart-link/providers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["providers"]}
    # 023 baseline 6 + 026 adds groq/gemini → 8 total
    assert {"github", "openai", "anthropic", "cohere", "slack", "smtp"}.issubset(ids)
    assert {"groq", "gemini"}.issubset(ids)
    for p in r.json()["providers"]:
        assert p["auth_method"] in {"oauth", "api_key", "credentials"}
