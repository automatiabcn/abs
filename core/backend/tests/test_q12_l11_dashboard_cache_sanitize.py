# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2D ITEM-2.2 — CodeQL py/clear-text-storage-sensitive-data (#32).

dashboard.py:50 wrote the aggregated admin payload to /tmp without masking
fields that could transitively contain provider keys or webhook secrets.

The fix:
1. `_sanitize_for_cache()` recursively masks values whose key matches secret
   patterns (api_key, token, secret, ...) or whose value starts with a
   well-known secret prefix (sk-, ghp_, xoxb-, AIza, ...).
2. `_write_cache()` writes with 0600 permissions (owner-only).
"""

from __future__ import annotations

import json
import os
import stat

from app.api.admin import dashboard as dashboard_mod
from app.api.admin.dashboard import _sanitize_for_cache, _write_cache


def test_sanitize_masks_api_key_field():
    payload = {"vault": {"openai_api_key": "sk-abc123def456ghi789"}}
    cleaned = _sanitize_for_cache(payload)
    assert cleaned["vault"]["openai_api_key"] != "sk-abc123def456ghi789"
    assert "***" in cleaned["vault"]["openai_api_key"]


def test_sanitize_masks_secret_token():
    payload = {"security": {"webhook_signing_secret": "whsec_abcdef0123456789"}}
    cleaned = _sanitize_for_cache(payload)
    assert "abcdef" not in cleaned["security"]["webhook_signing_secret"]


def test_sanitize_masks_by_prefix():
    payload = {"provider_response": "sk-deadbeef12345"}
    cleaned = _sanitize_for_cache(payload)
    assert cleaned["provider_response"] != "sk-deadbeef12345"


def test_sanitize_preserves_non_secret_fields():
    payload = {
        "billing": {"licenses_total": 42, "tier_breakdown": {"pro": 10}},
        "generated_at": 1234567890,
    }
    cleaned = _sanitize_for_cache(payload)
    assert cleaned["billing"]["licenses_total"] == 42
    assert cleaned["billing"]["tier_breakdown"] == {"pro": 10}
    assert cleaned["generated_at"] == 1234567890


def test_sanitize_handles_nested_lists():
    payload = {
        "audit_entries": [
            {"actor": "founder@example.com", "api_key": "sk-shouldbehidden0123"},
            {"actor": "ops@example.com", "token": "ghp_secretvalue1234567890"},
        ]
    }
    cleaned = _sanitize_for_cache(payload)
    assert cleaned["audit_entries"][0]["actor"] == "founder@example.com"
    assert cleaned["audit_entries"][0]["api_key"] != "sk-shouldbehidden0123"
    assert cleaned["audit_entries"][1]["token"] != "ghp_secretvalue1234567890"


def test_write_cache_strips_secrets_before_disk(tmp_path, monkeypatch):
    cache_file = tmp_path / "dash_cache.json"
    monkeypatch.setattr(dashboard_mod, "CACHE_PATH", cache_file)
    payload = {
        "vault": {"stripe_secret_key": "sk-leakedshouldntappear"},
        "billing": {"licenses_total": 1},
    }
    _write_cache(payload)
    content = cache_file.read_text()
    assert "sk-leakedshouldntappear" not in content
    parsed = json.loads(content)
    assert parsed["billing"]["licenses_total"] == 1


def test_write_cache_uses_owner_only_perms(tmp_path, monkeypatch):
    cache_file = tmp_path / "dash_perm.json"
    monkeypatch.setattr(dashboard_mod, "CACHE_PATH", cache_file)
    _write_cache({"billing": {"licenses_total": 0}})
    mode = stat.S_IMODE(os.stat(cache_file).st_mode)
    # 0o600 owner read/write only; group/other = 0
    assert mode & 0o077 == 0, f"file is world/group readable: {oct(mode)}"


def test_no_traceback_in_failed_cache(tmp_path, monkeypatch, caplog):
    # Pointing CACHE_PATH at a directory makes os.open fail; we expect
    # a debug-level swallow, not a thrown exception.
    monkeypatch.setattr(dashboard_mod, "CACHE_PATH", tmp_path)
    with caplog.at_level("DEBUG"):
        _write_cache({"x": 1})
    # No traceback string leaked into a log line
    for record in caplog.records:
        assert "Traceback" not in record.getMessage()
