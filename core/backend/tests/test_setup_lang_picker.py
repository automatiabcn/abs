"""023 Modul D — Setup wizard language picker."""

from __future__ import annotations

import json

import pytest

from app.config import settings


@pytest.fixture()
def _isolated_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_file = tmp_path / "setup_state.json"
    initial = {
        "completed": False,
        "current_step": 1,
        "completed_steps": [],
        "started_at": 0,
        "completed_at": None,
        "lang": "en",
        "data": {
            "admin": None,
            "license": None,
            "domain": None,
            "anthropic_configured": False,
            "providers_configured": [],
            "test_results": {},
        },
    }
    state_file.write_text(json.dumps(initial), encoding="utf-8")
    return tmp_path, state_file


def test_default_lang_is_en(client, _isolated_setup):
    r = client.get("/v1/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("lang") == "en"


def test_set_lang_to_tr_persists(client, _isolated_setup):
    _tmp, state_file = _isolated_setup
    r = client.post("/v1/setup/lang", json={"lang": "tr"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "lang": "tr"}
    state = json.loads(state_file.read_text())
    assert state["lang"] == "tr"


def test_set_lang_unsupported_returns_400(client, _isolated_setup):
    r = client.post("/v1/setup/lang", json={"lang": "de"})
    assert r.status_code == 400
