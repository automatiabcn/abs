"""Setup wizard end-to-end happy path + variations."""

from __future__ import annotations

import json
import time

import pytest

from app.config import settings
from app.licensing import generate_license


@pytest.fixture()
def _e2e_setup_state(tmp_path, monkeypatch):
    """Override data_dir + start with a fresh, NOT-completed state."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_file = tmp_path / "setup_state.json"
    state_file.write_text(
        json.dumps(
            {
                "completed": False,
                "current_step": 1,
                "completed_steps": [],
                "started_at": time.time(),
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
        ),
        encoding="utf-8",
    )
    return tmp_path, state_file


def _full_token():
    return generate_license(customer_id="cus_e2e", tier="self-host", seat_count=1)


def test_e2e_full_6_steps_completion(client, _e2e_setup_state, monkeypatch):
    _tmp, state_file = _e2e_setup_state
    token = _full_token()

    # Step 1 — admin
    r1 = client.post(
        "/v1/setup/step/admin",
        json={"email": "admin@x.co", "password": "supersecret123"},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["current_step"] == 2

    # Step 2 — license
    r2 = client.post(
        "/v1/setup/step/license",
        json={"license_key": token},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["current_step"] == 3

    # Step 3 — domain
    r3 = client.post(
        "/v1/setup/step/domain",
        json={"mode": "ip", "domain": None, "ssl_mode": "internal"},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["current_step"] == 4

    # Step 4 — anthropic
    r4 = client.post(
        "/v1/setup/step/anthropic",
        json={"anthropic_api_key": "sk-ant-mock-key-123456"},
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()["current_step"] == 5

    # Step 5 — providers (all empty optional)
    r5 = client.post(
        "/v1/setup/step/providers",
        json={},
    )
    assert r5.status_code == 200, r5.text
    assert r5.json()["current_step"] == 6

    # Step 6 — test
    r6 = client.post("/v1/setup/step/test", json={})
    assert r6.status_code == 200, r6.text

    # Final state
    final = json.loads(state_file.read_text())
    assert final["completed"] is True
    assert final["completed_at"] is not None
    assert sorted(final["completed_steps"]) == [
        "admin",
        "anthropic",
        "domain",
        "license",
        "providers",
        "test",
    ]


def test_e2e_lang_picker_persists(client, _e2e_setup_state):
    r = client.post("/v1/setup/lang", json={"lang": "es"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "lang": "es"}
    state = client.get("/v1/setup/status").json()
    assert state["lang"] == "es"


def test_e2e_step_out_of_order_rejected(client, _e2e_setup_state):
    """Skipping admin and going straight to license must 409."""
    token = _full_token()
    r = client.post(
        "/v1/setup/step/license",
        json={"license_key": token},
    )
    assert r.status_code == 409


def test_e2e_completion_idempotent(client, _e2e_setup_state):
    _tmp, state_file = _e2e_setup_state
    # Manually mark complete
    state = json.loads(state_file.read_text())
    state["completed"] = True
    state["current_step"] = 6
    state["completed_steps"] = [
        "admin",
        "license",
        "domain",
        "anthropic",
        "providers",
        "test",
    ]
    state_file.write_text(json.dumps(state))

    # Re-attempt admin step → 409 (already completed)
    r = client.post(
        "/v1/setup/step/admin",
        json={"email": "admin@x.co", "password": "supersecret123"},
    )
    assert r.status_code == 409
