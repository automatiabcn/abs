"""BUG-V3 — opt-in flip + quota-block events emit to abs.audit.

PROMISE.md vow:
  "every opt-in flip and quota-block event written to T-016 SOC2 audit log."

Two contracts pinned:
  1. `detect_and_emit_flip` writes nothing the first time (no prior
     state) but flips emit a `settings.optin.flip` audit row whenever
     ABS_ANTHROPIC_ENABLED toggles between boots.
  2. `quota_monitor.gate()` emits a `quota.block` audit row on every
     QuotaExceeded refusal.
"""

from __future__ import annotations

import logging

import pytest

from app.observability import quota_monitor
from app.observability.optin_state import detect_and_emit_flip


def _capture_audit(caplog: pytest.LogCaptureFixture) -> list[dict]:
    rows: list[dict] = []
    for record in caplog.records:
        if record.name == "abs.audit":
            payload = getattr(record, "audit", None)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def test_promise_v3_first_boot_no_emit(tmp_path, caplog):
    """First boot: no prior state → write the snapshot, never emit."""
    caplog.set_level(logging.INFO, logger="abs.audit")
    store = tmp_path / "last_optin_state.json"
    flipped = detect_and_emit_flip(current_enabled=True, path=store)
    assert flipped is False
    assert store.exists()
    assert not _capture_audit(caplog)


def test_promise_v3_optin_flip_emits_audit(tmp_path, caplog):
    """Toggling enabled false→true between boots emits one flip row."""
    caplog.set_level(logging.INFO, logger="abs.audit")
    store = tmp_path / "last_optin_state.json"
    # Seed previous state = false.
    detect_and_emit_flip(current_enabled=False, path=store)
    caplog.clear()
    # Now flip to true.
    flipped = detect_and_emit_flip(current_enabled=True, path=store)
    assert flipped is True
    rows = _capture_audit(caplog)
    actions = [r["action"] for r in rows]
    assert "settings.optin.flip" in actions, rows
    flip_row = next(r for r in rows if r["action"] == "settings.optin.flip")
    assert flip_row["outcome"] == "success"
    assert "anthropic_enabled=true" in str(flip_row.get("reason", ""))


def test_promise_v3_quota_gate_emits_block_audit(tmp_path, caplog, monkeypatch):
    """quota_monitor.gate() → QuotaExceeded → emits quota.block row."""
    caplog.set_level(logging.INFO, logger="abs.audit")
    ledger = tmp_path / "claude_tokens.jsonl"
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_LEDGER", str(ledger))
    monkeypatch.setattr(quota_monitor, "_ledger_path", lambda: ledger)
    monkeypatch.setenv("ABS_CLAUDE_MONTHLY_TOKEN_LIMIT", "1000")
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_BLOCK_PCT", "0.95")
    # Pre-load the ledger near the cap so a tiny request trips the gate.
    quota_monitor.record(tokens_in=950, tokens_out=0, model="claude")
    caplog.clear()
    with pytest.raises(quota_monitor.QuotaExceeded):
        quota_monitor.gate(requested_tokens=100)
    rows = _capture_audit(caplog)
    actions = [r["action"] for r in rows]
    assert "quota.block" in actions, rows
    block_row = next(r for r in rows if r["action"] == "quota.block")
    assert block_row["outcome"] == "denied"
    assert block_row.get("provider") == "anthropic"
