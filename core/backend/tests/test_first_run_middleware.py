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
    """Setup tamamlandiginda first-run middleware /setup'a yonlendirmez.

    Brief 4 R4 panel deprecation sonrasi /panel/login 308 (Next.js
    /admin'e), ama bu test middleware davranisini olcuyor — onemli olan
    302→/setup *olmadigi*. /healthz ile test ediyoruz cunku panel tarafi
    artik kendi redirect'ini issue ediyor.
    """
    r = client.get("/healthz", follow_redirects=False)
    assert r.status_code == 200

    # Sanity: /panel/login Brief 4 sonrasi 308 (panel.py decision), 302
    # olmamali (302 = first-run middleware → /setup, ki tamamlandi).
    p = client.get("/panel/login", follow_redirects=False)
    assert p.status_code != 302


def test_api_request_gets_503_json(incomplete_setup, client):
    """Sprint 2N FAZ F (P2 #2M-001) — Accept: application/json istekleri
    artık 307 HTML redirect yerine yapılandırılmış 503 JSON alır.
    API clients/SDK'lar `error` + `setup_url` alanlarını parse eder.
    """
    r = client.get(
        "/v1/license/status",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "setup_incomplete"
    assert body["setup_url"] == "/setup"
    assert "hint" in body
