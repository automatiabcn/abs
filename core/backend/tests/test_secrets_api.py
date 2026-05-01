"""013 — Vault rotation + status API testleri (admin auth zorunlu)."""

from __future__ import annotations


def _login(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


def test_rotate_unknown_key_400(client, monkeypatch):
    """Bilinmeyen vault key'i → 400."""
    import app.vault.runner as runner_mod

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: True)
    _login(client)
    r = client.post(
        "/v1/secrets/rotate", json={"key": "foo_bar_unknown", "new_value": "x"}
    )
    assert r.status_code == 400
    assert "Bilinmeyen" in r.json()["detail"]


def test_rotate_writes_and_invalidates_cache(client, monkeypatch):
    """write_secret + invalidate çağrıları yapılır."""
    import app.vault.cache as cache_mod
    import app.vault.runner as runner_mod

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: True)

    written: dict[str, str] = {}
    invalidated: list[bool] = []

    def fake_write(k, v):
        written[k] = v

    def fake_invalidate():
        invalidated.append(True)

    monkeypatch.setattr(runner_mod, "write_secret", fake_write)
    monkeypatch.setattr(cache_mod, "invalidate", fake_invalidate)
    # secrets.py içe aktarımları yenilensin diye lookup'ı modül seviyesinden invalidate olarak yamala
    import app.api.secrets as secrets_mod  # noqa: F401

    _login(client)
    r = client.post(
        "/v1/secrets/rotate",
        json={"key": "groq_api_key", "new_value": "gsk_rotated_xyz"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["key"] == "groq_api_key"
    assert written.get("groq_api_key") == "gsk_rotated_xyz"
    assert invalidated == [True]


def test_status_returns_configured_keys_no_cleartext(client, monkeypatch):
    """Status endpoint cleartext value DÖNDÜRMEZ."""
    import app.vault.runner as runner_mod

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: True)

    _login(client)
    r = client.get("/v1/secrets/status")
    assert r.status_code == 200
    body = r.json()
    assert body["vault_enabled"] is True
    assert isinstance(body["keys"], list)
    assert len(body["keys"]) >= 5
    for entry in body["keys"]:
        assert set(entry.keys()) == {"name", "configured"}
        # cleartext value YOK
        assert "value" not in entry


def test_secrets_status_requires_auth(client):
    """Auth yoksa 401."""
    r = client.get("/v1/secrets/status")
    assert r.status_code == 401
