"""Polish round R7 — /v1/admin/providers/status sanity guard.

The Settings → Providers tab leans on this endpoint to render a
"configured / missing" badge per provider. Failures here mean the UI either
silently goes blank or worse, exposes raw API keys.

Asserted invariants:

* Auth required (401 without Bearer).
* Returns 6 canonical providers in stable order with capitalised labels.
* ``configured`` flips with the matching ``settings`` attribute.
* No raw key value bleeds into the response.
"""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _login(client, monkeypatch) -> str:
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


def test_providers_status_requires_admin(client):
    r = client.get("/v1/admin/providers/status")
    assert r.status_code == 401


def test_providers_status_lists_six_canonical_providers(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/providers/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    items = body["providers"]
    assert isinstance(items, list)

    ids = [item["id"] for item in items]
    # Mirrors cascade.PROVIDER_ORDER_DEFAULT (free-first, Anthropic last) so
    # the Providers page cascade visual matches the real runtime order.
    assert ids == ["groq", "cerebras", "gemini", "cohere", "cloudflare", "anthropic"]

    labels = {item["id"]: item["label"] for item in items}
    assert labels == {
        "groq": "Groq",
        "cerebras": "Cerebras",
        "cloudflare": "Cloudflare",
        "gemini": "Gemini",
        "cohere": "Cohere",
        "anthropic": "Anthropic",
    }


def test_providers_status_reflects_configured_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "cohere_api_key", "ck_live_test_value")

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/providers/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    by_id = {item["id"]: item for item in r.json()["providers"]}
    assert by_id["groq"]["configured"] is False
    assert by_id["cohere"]["configured"] is True


def test_providers_status_never_leaks_raw_key(client, monkeypatch):
    secret = "ck_live_NEVER_SHIP_THIS"
    monkeypatch.setattr(settings, "cohere_api_key", secret)

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/providers/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # Raw secret must not appear anywhere in the wire payload.
    assert secret not in r.text
