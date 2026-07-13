"""Admin auth — login/logout/me + current_admin dep."""

from __future__ import annotations


def test_login_success_sets_cookie(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "logged_in"
    assert "abs_session" in r.cookies


def test_login_wrong_password_returns_401(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


def test_login_wrong_email_returns_401(client):
    r = client.post(
        "/auth/login",
        json={"email": "other@local", "password": "CHANGEME"},
    )
    assert r.status_code == 401


def test_me_without_cookie_returns_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"] == "No session"


def test_logout_clears_cookie(client):
    client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert r.json()["status"] == "logged_out"


def test_me_after_login_returns_email(client):
    client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    r = client.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "admin@local"
    assert "exp_at" in body
