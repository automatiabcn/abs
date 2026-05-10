# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2B BUG-34 — marketplace install persists via SQL + UI list reflects it."""

from __future__ import annotations

import pytest

from app.config import settings


def _bootstrap_admin_cookie(client, monkeypatch):
    """Bootstrap the panel session cookie via the existing admin login
    overlay so `current_admin` resolves without going through the OAuth
    flow."""
    import bcrypt

    monkeypatch.setattr(
        settings,
        "admin_password_bootstrap",
        "bootstrap-secret",
    )

    # Seed admin_credentials.json so the panel /auth/login overlay works.
    import json
    from pathlib import Path

    creds_path = Path(settings.data_dir) / "admin_credentials.json"
    creds_path.write_text(
        json.dumps(
            {
                "email": "admin@local",
                "password_hash": bcrypt.hashpw(
                    b"s3cret", bcrypt.gensalt()
                ).decode("utf-8"),
                "tenant_slug": "tnt-marketplace-test",
            }
        ),
        encoding="utf-8",
    )

    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "s3cret"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def test_install_persists_in_tenant_installed_plugins(client, monkeypatch):
    _bootstrap_admin_cookie(client, monkeypatch)
    r = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "tnt-marketplace-test"},
    )
    assert r.status_code in (200, 201), r.text

    # SQL row should exist.
    from sqlmodel import Session, select

    from app.db.models import TenantInstalledPlugin
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        row = db.execute(
            select(TenantInstalledPlugin).where(
                TenantInstalledPlugin.tenant_id == "tnt-marketplace-test",
                TenantInstalledPlugin.plugin_id == "slack-receiver",
                TenantInstalledPlugin.uninstalled_at.is_(None),
            )
        ).scalars().first()
        assert row is not None
        assert row.version == "1.0.0"


def test_installed_endpoint_reads_from_sql(client, monkeypatch):
    _bootstrap_admin_cookie(client, monkeypatch)
    client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "gmail-archiver", "tenant": "tnt-marketplace-test"},
    )

    r = client.get(
        "/v1/marketplace/installed?tenant=tnt-marketplace-test"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    plugin_ids = [row["plugin_id"] for row in body["installed"]]
    assert "gmail-archiver" in plugin_ids


def test_uninstall_marks_row_inactive(client, monkeypatch):
    _bootstrap_admin_cookie(client, monkeypatch)
    client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "linear-bridge", "tenant": "tnt-marketplace-test"},
    )

    r = client.delete(
        "/v1/marketplace/uninstall/linear-bridge?tenant=tnt-marketplace-test"
    )
    assert r.status_code == 200, r.text

    r2 = client.get(
        "/v1/marketplace/installed?tenant=tnt-marketplace-test"
    )
    plugin_ids = [row["plugin_id"] for row in r2.json()["installed"]]
    assert "linear-bridge" not in plugin_ids
