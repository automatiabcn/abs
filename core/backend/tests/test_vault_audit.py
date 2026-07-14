"""Vault audit log testleri."""

from __future__ import annotations

from pathlib import Path


def test_log_event_appends_jsonl(monkeypatch, tmp_path: Path):
    from app.config import settings
    from app.vault.audit import log_event, read_recent

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    log_event("write", "groq_api_key", source="setup_wizard")
    log_event("rotate", "anthropic_api_key", source="panel_api")

    audit = read_recent()
    assert len(audit) == 2
    assert audit[0]["event"] == "write"
    assert audit[0]["key"] == "groq_api_key"
    assert audit[0]["source"] == "setup_wizard"
    assert audit[1]["event"] == "rotate"
    # Cleartext value missing
    for entry in audit:
        for v in entry.values():
            if isinstance(v, str):
                assert "sk-ant" not in v
                assert "gsk_" not in v


def test_read_recent_limits_and_handles_missing(monkeypatch, tmp_path: Path):
    from app.config import settings
    from app.vault.audit import log_event, read_recent

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    # read_recent in empty directory → []
    assert read_recent() == []

    for i in range(120):
        log_event("write", f"key_{i}")
    last_5 = read_recent(limit=5)
    assert len(last_5) == 5
    assert last_5[-1]["key"] == "key_119"
