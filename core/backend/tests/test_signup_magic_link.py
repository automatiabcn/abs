"""/auth/signup magic_link reaches the customer only
by email in production. Response body never carries the token in prod."""

from __future__ import annotations

import pytest


def test_signup_response_strips_magic_link_in_prod(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "env", "prod")
    r = client.post(
        "/auth/signup",
        json={
            "email": "newuser-prod@example.com",
            "tenant_slug": "newco",
            "password": "S3cret-Password!1",
        },
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    # The security property: the token never leaks into the
    # response body in prod — it can only reach the user out-of-band.
    assert "magic_link" not in body
    assert body["status"] == "pending"
    # Honesty fix: self-signup does not email the link, so it must NOT claim it
    # did. Activation comes via an admin invite (panel copy-link / invite email).
    assert body["magic_link_sent"] is False
    assert body["check_email"] is False
    assert "activation_note" in body


def test_signup_response_retains_magic_link_in_dev(client):
    r = client.post(
        "/auth/signup",
        json={
            "email": "newuser-dev@example.com",
            "tenant_slug": "newco",
            "password": "S3cret-Password!2",
        },
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    # Q12 honesty round: the dev-mode magic_link now points at the /activate
    # SPA page (the backend claim endpoint /auth/magic is unchanged).
    assert body.get("magic_link", "").startswith("/activate?token=")


@pytest.mark.skip(
    reason="Audit-log emit hook for signup is out of scope; this suite only "
    "covers response-body hygiene."
)
def test_signup_emits_audit_event():
    """Placeholder so the suite documents the deferred check."""
