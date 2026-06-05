# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Saved workflow definitions — persistence the Builder's Save button needs.

Before this, /v1/workflows had synthesize/execute/jobs but NO way to persist a
named workflow definition (the panel "Save" was a no-op). These cover the new
CRUD under /v1/workflows/definitions, including tenant isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import bcrypt
import pytest

from app.config import settings


@pytest.fixture
def panel_admin(client):
    """Bootstrap the panel session cookie so `current_admin` resolves.

    admin_credentials.json is a SHARED file across the suite, so we back up
    any existing content and restore it on teardown — otherwise this fixture
    (which sorts before e.g. test_secrets_api) would leave a different
    password behind and 401 the next test's login.
    """
    creds_path = Path(settings.data_dir) / "admin_credentials.json"
    original = creds_path.read_text(encoding="utf-8") if creds_path.exists() else None
    creds_path.write_text(
        json.dumps(
            {
                "email": "admin@local",
                "password_hash": bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode(
                    "utf-8"
                ),
                "tenant_slug": "default",
            }
        ),
        encoding="utf-8",
    )
    r = client.post("/auth/login", json={"email": "admin@local", "password": "s3cret"})
    assert r.status_code == 200, r.text
    yield
    # Restore so we don't pollute later tests that share this file.
    if original is not None:
        creds_path.write_text(original, encoding="utf-8")
    else:
        creds_path.unlink(missing_ok=True)


_WF = {
    "id": "wf-test",
    "name": "Kira hatırlatma",
    "trigger": {"kind": "cron"},
    "nodes": [{"id": "n1", "kind": "llm"}],
    "edges": [],
}


def test_save_list_get_delete_roundtrip(client, panel_admin):
    # save
    r = client.post(
        "/v1/workflows/definitions",
        json={"name": "Kira hatırlatma", "definition": _WF},
    )
    assert r.status_code == 201, r.text
    saved = r.json()
    wf_id = saved["id"]
    assert saved["name"] == "Kira hatırlatma"
    assert saved["definition"]["nodes"][0]["id"] == "n1"

    # list
    r = client.get("/v1/workflows/definitions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert any(w["id"] == wf_id for w in body["workflows"])

    # get one
    r = client.get(f"/v1/workflows/definitions/{wf_id}")
    assert r.status_code == 200, r.text
    assert r.json()["definition"]["trigger"]["kind"] == "cron"

    # delete
    r = client.delete(f"/v1/workflows/definitions/{wf_id}")
    assert r.status_code == 204, r.text
    # gone
    r = client.get(f"/v1/workflows/definitions/{wf_id}")
    assert r.status_code == 404


def test_save_requires_auth(client):
    r = client.post(
        "/v1/workflows/definitions", json={"name": "x", "definition": _WF}
    )
    assert r.status_code in (401, 403)


def test_tenant_isolation(client, panel_admin):
    """A saved workflow from another tenant must not be listed/fetched."""
    from sqlmodel import Session

    from app.db.models import SavedWorkflow
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        other = SavedWorkflow(
            tenant_slug="other-tenant",
            name="secret",
            definition_json=json.dumps(_WF),
            created_by="someone@else",
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        other_id = other.id

    # current admin is tenant "default" → must not see "other-tenant" row
    body = client.get("/v1/workflows/definitions").json()
    assert all(w["id"] != other_id for w in body["workflows"])
    r = client.get(f"/v1/workflows/definitions/{other_id}")
    assert r.status_code == 404
    # and cannot delete it
    r = client.delete(f"/v1/workflows/definitions/{other_id}")
    assert r.status_code == 404
