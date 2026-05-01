"""032 Modul A — Admin auth login + IP whitelist + rate limit + JWT verify."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _set_password(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )


@pytest.fixture(autouse=True)
def _reset_failures():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def test_login_success_returns_jwt_and_sets_cookie(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["expires_in_seconds"] == 24 * 60 * 60
    assert "abs_admin" in r.cookies


def test_login_wrong_password_401(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    r = client.post("/v1/admin/login", json={"password": "WRONG"})
    assert r.status_code == 401


def test_login_disabled_when_hash_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", "")
    r = client.post("/v1/admin/login", json={"password": "anything"})
    assert r.status_code == 503


def test_ip_whitelist_blocks_non_whitelisted(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    monkeypatch.setattr(settings, "admin_ip_whitelist", "10.0.0.1,10.0.0.2")
    r = client.post(
        "/v1/admin/login",
        json={"password": "s3cret"},
        headers={"X-Forwarded-For": "9.9.9.9"},
    )
    assert r.status_code == 403


def test_ip_whitelist_allows_whitelisted(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    monkeypatch.setattr(settings, "admin_ip_whitelist", "10.0.0.1")
    r = client.post(
        "/v1/admin/login",
        json={"password": "s3cret"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert r.status_code == 200


def test_rate_limit_after_5_failures(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    for _ in range(5):
        r = client.post("/v1/admin/login", json={"password": "WRONG"})
        assert r.status_code == 401
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 429


def test_admin_me_requires_valid_jwt(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    # No bearer/cookie → 401
    r = client.get("/v1/admin/me")
    assert r.status_code == 401

    login = client.post("/v1/admin/login", json={"password": "s3cret"})
    token = login.json()["token"]
    r = client.get("/v1/admin/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "admin"


def test_admin_jwt_signature_change_rejects_old_tokens(client, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    login = client.post("/v1/admin/login", json={"password": "s3cret"})
    token = login.json()["token"]
    monkeypatch.setattr(settings, "admin_jwt_secret", "rotated-secret")
    r = client.get("/v1/admin/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
