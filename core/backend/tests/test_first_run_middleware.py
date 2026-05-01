"""012 — First-run redirect middleware testleri."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def incomplete_setup(monkeypatch, tmp_path: Path):
    """data_dir izole + setup_state.json YOK (autouse fixture'in yazdigini sil).
    Middleware'in 'incomplete' davranisini sinariz.
    """
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
    return data


@pytest.fixture
def completed_setup(monkeypatch, tmp_path: Path):
    """data_dir izole + setup_state.json `completed:true`."""
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    state = {
        "completed": True,
        "current_step": 6,
        "completed_steps": ["admin", "license", "domain", "anthropic", "providers", "test"],
        "started_at": time.time(),
        "completed_at": time.time(),
        "data": {},
    }
    (data / "setup_state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(settings, "data_dir", str(data))
    return data


def test_redirects_when_setup_incomplete(incomplete_setup, client):
    r = client.get("/panel", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/setup"


def test_no_redirect_for_whitelist(incomplete_setup, client):
    # /healthz whitelist
    r1 = client.get("/healthz")
    assert r1.status_code == 200
    # /v1/setup/status whitelist
    r2 = client.get("/v1/setup/status")
    assert r2.status_code == 200
    body = r2.json()
    assert body["completed"] is False


def test_no_redirect_when_completed(completed_setup, client):
    """Setup tamamlandiginda hicbir endpoint redirect'e gonderilmez."""
    r = client.get("/panel/login", follow_redirects=False)
    # /panel/login direkt 200 (auth gerekmez) → redirect yok
    assert r.status_code in (200, 401)
    assert r.status_code != 302


def test_api_request_gets_307_not_html(incomplete_setup, client):
    r = client.get(
        "/v1/license/status",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    # JSON Accept → 307 (POST/PUT için method preserve)
    assert r.status_code == 307
    assert r.headers["location"] == "/setup"
