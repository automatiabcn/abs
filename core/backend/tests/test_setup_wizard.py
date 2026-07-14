"""Setup Wizard 6-step state machine testleri."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.licensing import generate_license


@pytest.fixture
def isolated_setup(monkeypatch, tmp_path: Path):
    """data_dir + .env (empty) + license_key reset. Start with a cleared setup state."""
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "license_key", "")
    monkeypatch.setattr(settings, "env", "dev")
    settings.model_config["env_file"] = str(env_file)
    return {"data": data, "env": env_file}


def test_get_status_initial(isolated_setup, client):
    r = client.get("/v1/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["completed"] is False
    assert body["current_step"] == 1
    assert body["completed_steps"] == []


def test_admin_step_creates_credentials_file(isolated_setup, client):
    r = client.post(
        "/v1/setup/step/admin",
        json={"email": "owner@x.co", "password": "longSecret123"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_step"] == 2

    cred = isolated_setup["data"] / "admin_credentials.json"
    assert cred.is_file()
    payload = json.loads(cred.read_text())
    assert payload["email"] == "owner@x.co"
    assert payload["password_hash"].startswith("$2")  # bcrypt prefix
    assert payload["password_hash"] != "longSecret123"


def test_license_step_validates_jwt(isolated_setup, client):
    # Pass step 1
    client.post(
        "/v1/setup/step/admin",
        json={"email": "x@y.co", "password": "longSecret123"},
    )
    # Invalid token → 400
    r_bad = client.post(
        "/v1/setup/step/license", json={"license_key": "not.a.valid.jwt"}
    )
    assert r_bad.status_code == 400

    # Valid token → 200
    token = generate_license(
        "cust_setup", tier="self-host", seat_count=1, valid_days=30
    )
    r_ok = client.post("/v1/setup/step/license", json={"license_key": token})
    assert r_ok.status_code == 200, r_ok.text
    body = r_ok.json()
    assert body["current_step"] == 3
    assert body["tier"] == "self-host"

    state = json.loads((isolated_setup["data"] / "setup_state.json").read_text())
    assert state["data"]["license"]["jti"]


def test_domain_step_persists_to_env(isolated_setup, client):
    client.post(
        "/v1/setup/step/admin", json={"email": "x@y.co", "password": "longSecret123"}
    )
    token = generate_license("cust_dom", valid_days=30)
    client.post("/v1/setup/step/license", json={"license_key": token})

    r = client.post(
        "/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_step"] == 4
    env_text = isolated_setup["env"].read_text(encoding="utf-8")
    assert "ABS_SSL_MODE=internal" in env_text


def test_anthropic_step_validates_format(isolated_setup, client):
    client.post(
        "/v1/setup/step/admin", json={"email": "x@y.co", "password": "longSecret123"}
    )
    token = generate_license("cust_anth", valid_days=30)
    client.post("/v1/setup/step/license", json={"license_key": token})
    client.post("/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"})

    r_bad = client.post(
        "/v1/setup/step/anthropic", json={"anthropic_api_key": "invalidkey"}
    )
    # Pydantic v2 model_validator ValueError → FastAPI 422 (default).
    # test expected 400 (pre-Pydantic-v2); current
    # endpoint correctly returns 422 with the validator detail.
    assert r_bad.status_code == 422, r_bad.text

    r_ok = client.post(
        "/v1/setup/step/anthropic", json={"anthropic_api_key": "sk-ant-test12345"}
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["current_step"] == 5

    env_text = isolated_setup["env"].read_text(encoding="utf-8")
    assert "ABS_ANTHROPIC_API_KEY=sk-ant-test12345" in env_text


def test_providers_step_optional(isolated_setup, client):
    # Bring setup to step 5
    client.post(
        "/v1/setup/step/admin", json={"email": "x@y.co", "password": "longSecret123"}
    )
    client.post(
        "/v1/setup/step/license",
        json={"license_key": generate_license("cust_prov", valid_days=30)},
    )
    client.post("/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"})
    client.post(
        "/v1/setup/step/anthropic", json={"anthropic_api_key": "sk-ant-test12345"}
    )

    # Empty body → atla, current_step=6
    r_empty = client.post("/v1/setup/step/providers", json={})
    assert r_empty.status_code == 200, r_empty.text
    assert r_empty.json()["current_step"] == 6
    assert r_empty.json()["configured"] == []


def test_complete_step_sets_completed_flag(isolated_setup, client):
    # Proceed up to step 5
    client.post(
        "/v1/setup/step/admin", json={"email": "x@y.co", "password": "longSecret123"}
    )
    client.post(
        "/v1/setup/step/license",
        json={"license_key": generate_license("cust_test", valid_days=30)},
    )
    client.post("/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"})
    client.post(
        "/v1/setup/step/anthropic", json={"anthropic_api_key": "sk-ant-test12345"}
    )
    client.post(
        "/v1/setup/step/providers",
        json={"groq_api_key": "gsk_dummy123"},
    )

    r = client.post("/v1/setup/step/test", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["completed"] is True
    assert body["current_step"] == 6

    state = json.loads((isolated_setup["data"] / "setup_state.json").read_text())
    assert state["completed"] is True
    assert state["completed_at"] is not None


def _advance_to_providers(client) -> None:
    client.post(
        "/v1/setup/step/admin", json={"email": "x@y.co", "password": "longSecret123"}
    )
    client.post(
        "/v1/setup/step/license",
        json={"license_key": generate_license("cust_fmt", valid_days=30)},
    )
    client.post("/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"})
    client.post(
        "/v1/setup/step/anthropic", json={"anthropic_api_key": "sk-ant-test12345"}
    )


def test_providers_step_rejects_malformed_key(isolated_setup, client):
    """A key pasted into the wrong field (no 'gsk_' prefix) is rejected with a
    400 + per-field reason, and nothing is persisted (step stays at 5)."""
    _advance_to_providers(client)
    r = client.post(
        "/v1/setup/step/providers", json={"groq_api_key": "sk-this-is-an-openai-key"}
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_provider_key_format"
    assert "groq_api_key" in detail["fields"]
    # step did not advance — the malformed key was not stored
    assert client.get("/v1/setup/status").json()["current_step"] == 5


def test_providers_step_strips_whitespace_and_accepts_valid(isolated_setup, client):
    _advance_to_providers(client)
    r = client.post(
        "/v1/setup/step/providers", json={"groq_api_key": "  gsk_validlookingkey123  "}
    )
    assert r.status_code == 200, r.text
    assert r.json()["configured"] == ["groq_api_key"]


def test_providers_step_rejects_bad_cf_account_id(isolated_setup, client):
    _advance_to_providers(client)
    r = client.post("/v1/setup/step/providers", json={"cf_account_id": "not-32-hex"})
    assert r.status_code == 400, r.text
    assert "cf_account_id" in r.json()["detail"]["fields"]


def test_a_customer_without_a_license_can_finish_the_wizard(isolated_setup, client):
    """The free tier has to be reachable through the front door.

    Step 2 used to be `license_key: str = Field(..., min_length=10)`, so the wizard
    could not be completed without a key — on a product whose pitch is that the free
    tier is the default, and on a screen that said so in as many words. A customer
    with no key got to step 2 and stopped there.
    """
    client.post(
        "/v1/setup/step/admin",
        json={"email": "free@tier.co", "password": "longSecret123"},
    )

    r = client.post("/v1/setup/step/license", json={})
    assert r.status_code == 200, r.text
    assert r.json()["tier"] == "free"
    assert r.json()["current_step"] == 3

    # And the rest of it, with no keys anywhere: this is the zero-key install.
    assert (
        client.post(
            "/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/setup/step/anthropic", json={"skip_paid_providers": True}
        ).status_code
        == 200
    )
    assert client.post("/v1/setup/step/providers", json={}).status_code == 200
    assert client.post("/v1/setup/step/test", json={}).status_code == 200

    status = client.get("/v1/setup/status").json()
    assert status["completed"] is True
    assert status["data"]["license"]["mode"] == "demo"


def test_an_empty_license_string_is_the_same_as_no_license(isolated_setup, client):
    """The wizard posts "" when the free-tier box is ticked, not an absent field."""
    client.post(
        "/v1/setup/step/admin",
        json={"email": "free2@tier.co", "password": "longSecret123"},
    )
    r = client.post("/v1/setup/step/license", json={"license_key": "   "})
    assert r.status_code == 200, r.text
    assert r.json()["tier"] == "free"


def test_a_bad_license_key_is_still_refused(isolated_setup, client):
    """Optional is not the same as unchecked: a key that is present must verify."""
    client.post(
        "/v1/setup/step/admin",
        json={"email": "bad@key.co", "password": "longSecret123"},
    )
    r = client.post("/v1/setup/step/license", json={"license_key": "not.a.valid.jwt"})
    assert r.status_code == 400
    assert "Invalid license" in r.text


def _walk_to_the_test_step(client) -> None:
    client.post(
        "/v1/setup/step/admin",
        json={"email": "dry@run.co", "password": "longSecret123"},
    )
    client.post("/v1/setup/step/license", json={})
    client.post("/v1/setup/step/domain", json={"mode": "ip", "ssl_mode": "internal"})
    client.post("/v1/setup/step/anthropic", json={"skip_paid_providers": True})
    client.post("/v1/setup/step/providers", json={})


def test_you_can_test_your_keys_without_ending_the_wizard(isolated_setup, client):
    """Step 6 used to test and finish in one irreversible click.

    `/step/test` sets completed=True, and every earlier step then answers 409 —
    so the moment a customer learned their Groq key was wrong was the same moment
    they lost the ability to go back and fix it. The dry run tests and writes
    nothing; the wizard is still open behind it.
    """
    _walk_to_the_test_step(client)

    r = client.post("/v1/setup/test", json={})
    assert r.status_code == 200, r.text
    assert "test_results" in r.json()

    status = client.get("/v1/setup/status").json()
    assert status["completed"] is False
    assert status["current_step"] == 6

    # ...and going back to fix a key still works, which is the whole point.
    assert client.post("/v1/setup/step/test", json={}).status_code == 200
    assert client.get("/v1/setup/status").json()["completed"] is True


def test_the_dry_run_refuses_once_setup_is_done(isolated_setup, client):
    _walk_to_the_test_step(client)
    client.post("/v1/setup/step/test", json={})
    assert client.post("/v1/setup/test", json={}).status_code == 409
