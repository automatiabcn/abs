"""Update channel manifest fetch + check/apply endpoint testleri."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx


def _login(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(
        settings, "update_manifest_url", "https://abs.local/manifest.json"
    )
    # 015 — these tests do not mock signature, bypass with dev mode (False)
    monkeypatch.setattr(settings, "update_signature_required", False)
    # Ensure setup state also exists in tmp data_dir so first-run middleware doesn't redirect
    (tmp_path / "setup_state.json").write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": [],
                "data": {},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
@respx.mock
async def test_check_returns_state_current_when_versions_match(
    isolated_data_dir, monkeypatch
):
    from app.main import app
    from app.update.manifest import fetch_manifest, update_state

    monkeypatch.setattr(app, "version", "0.1.0")
    respx.get("https://abs.local/manifest.json").mock(
        return_value=httpx.Response(200, json={"current_version": "0.1.0"})
    )
    manifest = await fetch_manifest(force=True)
    state = update_state(manifest, app.version)
    assert state["state"] == "current"
    assert state["current"] == "0.1.0"


@pytest.mark.asyncio
@respx.mock
async def test_check_returns_available_when_higher_version(
    isolated_data_dir, monkeypatch
):
    from app.main import app
    from app.update.manifest import fetch_manifest, update_state

    monkeypatch.setattr(app, "version", "0.1.0")
    respx.get("https://abs.local/manifest.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "current_version": "0.2.0",
                "changelog_summary": "RAG hybrid",
                "released_at": "2026-04-30T00:00:00Z",
            },
        )
    )
    manifest = await fetch_manifest(force=True)
    state = update_state(manifest, app.version)
    assert state["state"] == "available"
    assert state["latest"] == "0.2.0"
    assert state["changelog_summary"] == "RAG hybrid"


@pytest.mark.asyncio
@respx.mock
async def test_check_returns_critical_when_critical_flag(
    isolated_data_dir, monkeypatch
):
    from app.main import app
    from app.update.manifest import fetch_manifest, update_state

    monkeypatch.setattr(app, "version", "0.1.0")
    respx.get("https://abs.local/manifest.json").mock(
        return_value=httpx.Response(
            200, json={"current_version": "0.2.0", "critical": True}
        )
    )
    manifest = await fetch_manifest(force=True)
    state = update_state(manifest, app.version)
    assert state["state"] == "critical"
    assert state["critical"] is True


def test_apply_writes_pending_flag(isolated_data_dir, client):
    _login(client)
    r = client.post("/v1/update/apply")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["pending"]["status"] == "pending"
    flag = isolated_data_dir / "update_pending.json"
    assert flag.is_file()
    payload = json.loads(flag.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"


def test_compare_versions_handles_malformed():
    from app.update.manifest import compare_versions

    assert compare_versions("0.1.0", "0.2.0") == -1
    assert compare_versions("1.0.0", "0.9.9") == 1
    assert compare_versions("0.1.0", "0.1.0") == 0
    # Malformed → 0, no exception
    assert compare_versions("0.1", "abc") == 0
    assert compare_versions("", "1.0.0") == 0


def test_pending_endpoint_returns_none_when_no_flag(isolated_data_dir, client):
    _login(client)
    r = client.get("/v1/update/pending")
    assert r.status_code == 200
    assert r.json()["status"] == "none"
