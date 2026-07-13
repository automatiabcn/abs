"""Sprint 2I UAT-019 — POST /v1/admin/providers/{id}/test is rate-limited
(5/min) so abusive automation cannot burn through real provider quota."""

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
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def _patch_provider_call(monkeypatch):
    """Skip the real cascade call so the test cannot reach a live API."""

    async def fake(*_a, **_kw):
        from app.providers.schemas import ProviderResponse

        return ProviderResponse(text="ok", model="fake", provider="groq", elapsed_ms=1)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake)


def test_test_provider_caps_at_5_per_minute(client, monkeypatch):
    _patch_provider_call(monkeypatch)
    monkeypatch.setattr(settings, "groq_api_key", "real-value")
    token = _admin_token(client, monkeypatch)
    headers = {"Cookie": f"abs_admin={token}"}

    # 5 calls succeed; the 6th hits @limiter.limit("5/minute") → 429.
    for _ in range(5):
        r = client.post("/v1/admin/providers/groq/test", headers=headers)
        assert r.status_code == 200, r.text
    r6 = client.post("/v1/admin/providers/groq/test", headers=headers)
    assert r6.status_code == 429
    assert r6.headers.get("Retry-After")
