"""011 — Demo mode 14-day countdown testleri."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_demo(monkeypatch, tmp_path: Path):
    """data_dir + license_key reset. Setup state completed:true yazilir
    (first-run middleware /demo-status'u redirect etmesin)."""
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "license_key", "")
    (tmp_path / "setup_state.json").write_text(
        json.dumps(
            {"completed": True, "current_step": 6, "completed_steps": [], "data": {}}
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_start_demo_writes_state(isolated_demo):
    from app.licensing.demo import _state_path, start_demo

    state = start_demo()
    assert state["started_at"] > 0
    assert state["expires_at"] > state["started_at"]
    assert state["duration_days"] == 14
    p = _state_path()
    assert p.is_file()
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["started_at"] == state["started_at"]


def test_start_demo_idempotent(isolated_demo):
    from app.licensing.demo import start_demo

    s1 = start_demo()
    time.sleep(0.01)
    s2 = start_demo()
    assert s1["started_at"] == s2["started_at"]
    assert s1["expires_at"] == s2["expires_at"]


def test_status_active_within_14_days(isolated_demo):
    from app.licensing.demo import start_demo, status

    start_demo()
    s = status()
    assert s["started"] is True
    assert s["active"] is True
    assert s["expired"] is False
    assert 0 < s["days_remaining"] <= 14


def test_status_expired_after_14_days(isolated_demo):
    from app.licensing.demo import _state_path, status

    p = _state_path()
    past = time.time() - 1
    p.write_text(
        json.dumps(
            {
                "started_at": past - 14 * 86400,
                "expires_at": past,
                "duration_days": 14,
            }
        ),
        encoding="utf-8",
    )
    s = status()
    assert s["started"] is True
    assert s["expired"] is True
    assert s["active"] is False
    assert s["days_remaining"] == 0


def test_is_active_bypassed_when_license_key_set(isolated_demo, monkeypatch):
    from app.config import settings
    from app.licensing.demo import is_active, start_demo, status

    start_demo()
    assert status()["active"] is True
    monkeypatch.setattr(settings, "license_key", "dummy_jwt_value")
    assert is_active() is False


def test_demo_status_endpoint(isolated_demo, client):
    from app.licensing.demo import start_demo

    start_demo()
    r = client.get("/v1/license/demo-status")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert body["active"] is True
