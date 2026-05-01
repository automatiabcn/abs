"""022 Modul C — Admin demo reset endpoint."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.config import settings


@pytest.fixture()
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    state_file = tmp_path / "demo_state.json"
    # setup_state.json (first-run middleware whitelist için)
    (tmp_path / "setup_state.json").write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": ["admin", "license", "domain", "anthropic", "providers", "test"],
                "started_at": time.time(),
                "completed_at": time.time(),
                "data": {},
            }
        )
    )
    return tmp_path, state_file


def test_demo_reset_no_auth_returns_401(client, _isolated_data_dir):
    r = client.post("/v1/admin/demo/reset")
    assert r.status_code == 401


def test_demo_reset_wrong_token_returns_403(client, _isolated_data_dir):
    r = client.post(
        "/v1/admin/demo/reset", headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 403


def test_demo_reset_valid_token_clears_state(client, _isolated_data_dir):
    _tmp, state_file = _isolated_data_dir
    state_file.write_text('{"started_at": 1, "expires_at": 2}')
    assert state_file.is_file()

    r = client.post(
        "/v1/admin/demo/reset",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["existed_before"] is True
    assert not state_file.is_file()

    # Idempotent: ikinci kez 200 ama existed_before False
    r2 = client.post(
        "/v1/admin/demo/reset",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r2.status_code == 200
    assert r2.json()["existed_before"] is False
