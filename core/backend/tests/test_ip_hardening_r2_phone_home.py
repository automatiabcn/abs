# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""IP hardening — phone-home + 7-day grace tests.

Coverage (4 tests):
    1. phone-home offline grace ≤ 7 days → operate
    2. phone-home offline grace > 7 days → block (offline_grace_expired)
    3. phone-home first-boot activation calls the server exactly once
    4. ABS_BUILD_HASH env round-trips through phone_home._read_build_hash()
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.licensing import generate_license
from app.licensing import phone_home as ph_mod


def test_phone_home_offline_grace_within_window(tmp_path, monkeypatch):
    state_path = tmp_path / "license_activation.json"
    last_check = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    state_path.write_text(
        json.dumps({"valid": True, "watermark": "wm123", "last_check": last_check})
    )
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    result = ph_mod._check_offline_grace(RuntimeError("connect failed"))
    assert result["valid"] is True
    assert "offline_grace" in result["reason"]


def test_phone_home_offline_grace_expired(tmp_path, monkeypatch):
    state_path = tmp_path / "license_activation.json"
    last_check = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    state_path.write_text(
        json.dumps({"valid": True, "watermark": "wm123", "last_check": last_check})
    )
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    result = ph_mod._check_offline_grace(RuntimeError("connect failed"))
    assert result["valid"] is False
    assert result["reason"] == "offline_grace_expired"


def test_phone_home_first_boot_activation_calls_server(tmp_path, monkeypatch):
    state_path = tmp_path / "license_activation.json"
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    captured = {"calls": 0, "payload": None}

    class _MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"valid": True, "watermark": "wm-test", "expires_at": 1735689600}

    class _MockClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, _url, json):  # noqa: A002 — match httpx kwarg
            captured["calls"] += 1
            captured["payload"] = json
            return _MockResponse()

    monkeypatch.setattr(ph_mod.httpx, "AsyncClient", _MockClient)

    token = generate_license("cust_pb", valid_days=10)
    result = asyncio.run(ph_mod.activate_online(token, "fp-deadbeef"))

    assert captured["calls"] == 1
    assert captured["payload"]["machine_fp"] == "fp-deadbeef"
    assert result["valid"] is True
    persisted = json.loads(Path(state_path).read_text())
    assert persisted["watermark"] == "wm-test"
    assert "last_check" in persisted


def test_build_hash_embedded(monkeypatch):
    monkeypatch.setenv("ABS_BUILD_HASH", "abc123def456-deadbeefcafef00d")
    assert ph_mod._read_build_hash() == "abc123def456-deadbeefcafef00d"

    monkeypatch.delenv("ABS_BUILD_HASH", raising=False)
    assert ph_mod._read_build_hash() == "unknown"
