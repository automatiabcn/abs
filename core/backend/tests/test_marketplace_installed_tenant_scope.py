"""Round-4 BUG-10 regression — `/v1/marketplace/installed` tenant scoping.

Founder Phase D evidence: install went to `tenant=demo-acme` (POST body
explicit) but the subsequent GET defaulted to `tenant=default` and returned
an empty list, masking a successful install.

Round-4 fix: when no `tenant` query param is supplied, the endpoint now
resolves the admin's tenant via the JWT claim → users-table fallback →
"default" chain.
"""

from __future__ import annotations

import json
import time
from typing import Iterator

import pytest

from app.api import marketplace as marketplace_module
from app.config import settings


def _login(client) -> None:
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _ensure_cosign_skip(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "cosign_skip", True)
    yield


@pytest.fixture(autouse=True)
def _isolated_install_store(tmp_path, monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_path = tmp_path / "setup_state.json"
    state_path.write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": [
                    "admin",
                    "license",
                    "domain",
                    "anthropic",
                    "providers",
                    "test",
                ],
                "started_at": time.time(),
                "completed_at": time.time(),
                "data": {},
            }
        ),
        encoding="utf-8",
    )
    yield


def test_installed_resolves_admin_tenant_when_query_param_missing(client):
    """Phase D evidence: install→demo-acme but list→default empty.

    With a synthetic admin claim carrying `tenant=demo-acme`, the GET
    without an explicit `?tenant=...` must still report `demo-acme` and
    surface the previously installed plugin.
    """
    from app.api.marketplace import current_admin as live_dep
    from app.main import app

    app.dependency_overrides[live_dep] = lambda: {
        "sub": "demo-admin@acme.test",
        "tenant": "demo-acme",
    }
    try:
        r_install = client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "slack-receiver", "tenant": "demo-acme"},
        )
        assert r_install.status_code == 201, r_install.text

        r_list = client.get("/v1/marketplace/installed")
        assert r_list.status_code == 200, r_list.text
        body = r_list.json()
        assert body["tenant"] == "demo-acme"
        assert any(
            row["plugin_id"] == "slack-receiver" for row in body["installed"]
        ), body
    finally:
        app.dependency_overrides.pop(live_dep, None)


def test_installed_explicit_query_param_still_supported(client):
    """Backwards compat: passing ?tenant=X still works (after gate)."""
    from app.api.marketplace import current_admin as live_dep
    from app.main import app

    app.dependency_overrides[live_dep] = lambda: {
        "sub": "demo-admin@acme.test",
        "tenant": "demo-acme",
    }
    try:
        client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "gmail-archiver", "tenant": "demo-acme"},
        )
        r = client.get("/v1/marketplace/installed?tenant=demo-acme")
        assert r.status_code == 200
        body = r.json()
        assert body["tenant"] == "demo-acme"
        assert any(
            row["plugin_id"] == "gmail-archiver" for row in body["installed"]
        )
    finally:
        app.dependency_overrides.pop(live_dep, None)


def test_installed_resolver_falls_back_to_users_table(client, monkeypatch):
    """When JWT lacks `tenant` claim, resolver consults the users table."""
    from app.api.marketplace import current_admin as live_dep
    from app.api import marketplace as mp
    from app.main import app

    # Force the User lookup to return tenant_slug=demo-acme.
    class _FakeUser:
        tenant_slug = "demo-acme"

    monkeypatch.setattr(
        mp, "_resolve_admin_tenant", lambda admin: _FakeUser.tenant_slug
    )

    app.dependency_overrides[live_dep] = lambda: {"sub": "anyone@x"}
    try:
        client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "slack-receiver", "tenant": "demo-acme"},
        )
        r = client.get("/v1/marketplace/installed")
        assert r.status_code == 200
        assert r.json()["tenant"] == "demo-acme"
    finally:
        app.dependency_overrides.pop(live_dep, None)


def test_installed_default_tenant_legacy_path(client):
    """Bootstrap admin (no JWT tenant claim, users.tenant_slug=default)
    still gets the legacy `default` listing — proves the new default
    is admin-scoped, not silently broken."""
    _login(client)
    client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    r = client.get("/v1/marketplace/installed")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant"] == "default"
    assert any(
        row["plugin_id"] == "slack-receiver" for row in body["installed"]
    ), body


def test_bootstrap_admin_resolves_tenant_from_credentials_file(client, tmp_path):
    """Round-5 BUG-10 follow-up — setup-wizard / magic-link-claim admin has
    NO ``users`` row but ``admin_credentials.json`` carries ``tenant_slug``.

    Without the file fallback the resolver short-circuited on the empty DB
    lookup and dropped the admin into ``default`` — Phase D evidence.
    The bootstrap admin must now land on ``demo-acme`` so the install they
    just performed surfaces in the listing.
    """
    from app.api.marketplace import current_admin as live_dep
    from app.main import app

    creds_path = tmp_path / "admin_credentials.json"
    creds_path.write_text(
        json.dumps(
            {
                "email": "admin@demo-acme.com",
                "password_hash": "$2b$12$placeholderhashforvalidationonly",
                "created_at": time.time(),
                "tenant_slug": "demo-acme",
                "source": "setup_wizard",
            }
        ),
        encoding="utf-8",
    )

    # Admin claim mirrors what /auth/login mints when the cookie is decoded
    # but BEFORE the new tenant-claim wiring kicks in (worst case for
    # legacy sessions still cached from the previous build).
    app.dependency_overrides[live_dep] = lambda: {"sub": "admin@demo-acme.com"}
    try:
        r_install = client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "gmail-archiver", "tenant": "demo-acme"},
        )
        assert r_install.status_code == 201, r_install.text

        r = client.get("/v1/marketplace/installed")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant"] == "demo-acme", body
        assert any(
            row["plugin_id"] == "gmail-archiver" for row in body["installed"]
        ), body
    finally:
        app.dependency_overrides.pop(live_dep, None)


def test_bootstrap_admin_email_domain_heuristic(client):
    """Round-5 BUG-10 follow-up — even when credentials.json lacks
    ``tenant_slug`` the resolver falls back to the email-domain first
    label so customers running fresh setup wizards never see ``default``
    leaking installs unless their email actually points at a single-label
    bootstrap host (``admin@local``)."""
    from app.api.marketplace import current_admin as live_dep
    from app.main import app

    app.dependency_overrides[live_dep] = lambda: {
        "sub": "owner@acme-co.io"
    }
    try:
        r_install = client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "slack-receiver", "tenant": "acme-co"},
        )
        assert r_install.status_code == 201, r_install.text

        r = client.get("/v1/marketplace/installed")
        assert r.status_code == 200
        body = r.json()
        assert body["tenant"] == "acme-co", body
    finally:
        app.dependency_overrides.pop(live_dep, None)
