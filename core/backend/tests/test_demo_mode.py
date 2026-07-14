"""The free window, seen through its old name.

`licensing.demo` used to own a fourteen-day clock of its own. It does not any
more — `licensing.trial` is the only clock, the window is seven days, and this
module is the vocabulary the panel, the wizard and the MCP tool still speak.
These tests pin that the old callers still get answers, and that the answers are
the trial's.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_demo(monkeypatch, tmp_path: Path):
    """data_dir + license_key reset. Setup state completed:true written
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


def test_start_demo_opens_the_seven_day_trial(isolated_demo):
    from app.licensing.demo import DEMO_DURATION_DAYS, start_demo

    state = start_demo()
    assert state["started_at"] > 0
    assert state["expires_at"] > state["started_at"]
    assert state["duration_days"] == DEMO_DURATION_DAYS == 7, (
        "the retired fourteen-day demo was a second free window on the same empty "
        "key — twice as long as the trial the product is priced on"
    )

    # One clock, one file.
    on_disk = json.loads((isolated_demo / "trial.json").read_text(encoding="utf-8"))
    assert on_disk["started_at"] == state["started_at"]


def test_start_demo_idempotent(isolated_demo):
    from app.licensing.demo import start_demo

    s1 = start_demo()
    time.sleep(0.01)
    s2 = start_demo()
    assert s1["started_at"] == s2["started_at"]
    assert s1["expires_at"] == s2["expires_at"]


def test_status_active_within_the_window(isolated_demo):
    from app.licensing.demo import start_demo, status

    start_demo()
    s = status()
    assert s["started"] is True
    assert s["active"] is True
    assert s["expired"] is False
    assert 0 < s["days_remaining"] <= 7


def test_status_expired_after_the_window(isolated_demo):
    from app.licensing.demo import status

    started = time.time() - 30 * 86400
    (isolated_demo / "trial.json").write_text(
        json.dumps({"started_at": started, "seen_at": started}), encoding="utf-8"
    )

    s = status()
    assert s["started"] is True
    assert s["expired"] is True
    assert s["active"] is False
    assert s["days_remaining"] == 0


def test_a_legacy_demo_state_still_dates_the_install(isolated_demo):
    """Installs from before the rename have `demo_state.json` and no `trial.json`.

    Their free window started when *they* started. If the trial dated itself from
    the upgrade instead, shipping the subscription would have handed every one of
    them a brand new week.
    """
    from app.licensing.demo import status

    started = time.time() - 10 * 86400
    (isolated_demo / "demo_state.json").write_text(
        json.dumps({"started_at": started, "expires_at": started + 14 * 86400}),
        encoding="utf-8",
    )

    assert status()["active"] is False


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
