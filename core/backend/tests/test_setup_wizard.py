"""012 — Setup Wizard 6-step state machine testleri."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.licensing import generate_license


@pytest.fixture
def isolated_setup(monkeypatch, tmp_path: Path):
    """data_dir + .env (boş) + license_key reset. Setup state silinmiş başlasın."""
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
    # Adım 1'i geç
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
    token = generate_license("cust_setup", tier="self-host", seat_count=1, valid_days=30)
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
    # Q12-L19 Round 11: test expected 400 (pre-Pydantic-v2); current
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
    # Setup'ı 5. adıma getir
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
    # 5. adıma kadar geç
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
