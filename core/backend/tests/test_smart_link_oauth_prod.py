"""GitHub OAuth production: state DB cache, code exchange, refresh, revoke."""

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


def _mock_oauth_post(
    monkeypatch,
    *,
    code_token: str,
    refresh_token: str | None,
    refreshed_token: str | None = None,
):
    """GitHub, answering both grants: the initial code exchange and the refresh.

    The old helper answered only one, which was enough, because /github/refresh
    never called GitHub — it re-encrypted the token it already had and reported
    `rotated: true`. A test that mocks the call the code does not make cannot
    notice that the code does not make it.
    """
    real_post = httpx.Client.post

    def _post(self, url, *args, **kwargs):
        url_str = str(url)
        if "github.com" in url_str and "access_token" in url_str:
            body = kwargs.get("json") or {}
            if body.get("grant_type") == "refresh_token":
                if refreshed_token is None:
                    return _FakeRsp(400, {"error": "unsupported_grant_type"})
                return _FakeRsp(
                    200,
                    {
                        "access_token": refreshed_token,
                        "refresh_token": "ghr_rotated",
                        "expires_in": 28800,
                    },
                )
            payload = {
                "access_token": code_token,
                "scope": "repo",
                "token_type": "bearer",
            }
            if refresh_token:
                payload["refresh_token"] = refresh_token
                payload["expires_in"] = 28800
            return _FakeRsp(200, payload)
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _post)


def _connect(client) -> None:
    state = client.post(
        "/v1/smart-link/github/authorize", json={"redirect_url": "https://x"}
    ).json()["state"]
    client.get(f"/v1/smart-link/github/callback?code=x&state={state}")


def test_refresh_requires_admin(client, monkeypatch):
    _mock_oauth_post(
        monkeypatch,
        code_token="ghs_initial",
        refresh_token="ghr_1",
        refreshed_token="ghs_second",
    )
    _connect(client)

    assert client.post("/v1/smart-link/github/refresh").status_code == 401
    assert (
        client.post(
            "/v1/smart-link/github/refresh", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 403
    )


def test_refresh_actually_replaces_the_stored_token(client, monkeypatch):
    """The point of Refresh. It used to re-encrypt the same bytes under the same
    key and say `rotated: true` — so an operator refreshing a token they believed
    was leaked kept the leaked token, with a green tick over it."""
    from app.smart_link.vault_secrets import decrypt_secret

    _mock_oauth_post(
        monkeypatch,
        code_token="ghs_initial",
        refresh_token="ghr_1",
        refreshed_token="ghs_second",
    )
    _connect(client)
    assert decrypt_secret("github_oauth_token") == "ghs_initial"

    r = client.post(
        "/v1/smart-link/github/refresh",
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rotated"] is True

    # The stored credential is a different one. That is what rotation means.
    assert decrypt_secret("github_oauth_token") == "ghs_second"
    assert decrypt_secret("github_oauth_token__refresh") == "ghr_rotated"


def test_refresh_that_cannot_happen_says_so_and_changes_nothing(client, monkeypatch):
    """GitHub only issues refresh tokens to OAuth apps with token expiration on.
    Without one there is nothing to rotate with — and claiming otherwise is the
    bug this replaced."""
    from app.smart_link.vault_secrets import decrypt_secret

    _mock_oauth_post(monkeypatch, code_token="ghs_only", refresh_token=None)
    _connect(client)

    r = client.post(
        "/v1/smart-link/github/refresh",
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r.status_code == 409
    assert "unchanged" in r.json()["detail"]
    assert decrypt_secret("github_oauth_token") == "ghs_only"


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
