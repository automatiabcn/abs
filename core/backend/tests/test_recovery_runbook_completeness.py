"""027 Modul D — Recovery runbook completeness."""

from __future__ import annotations

from pathlib import Path


def _runbook() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "vault-recovery-runbook.md"


def test_recovery_runbook_has_4_scenarios_and_min_words():
    p = _runbook()
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert len(text.split()) >= 800, "runbook < 800 words"
    for scenario in (
        "Scenario 1 — Master key file deleted",
        "Scenario 2 — Master key compromised",
        "Scenario 3 — Vault file corrupted",
        "Scenario 4 — Partial secret corruption",
    ):
        assert scenario in text, f"missing: {scenario}"
    # Each scenario has Recovery + Verification + Post-mortem sections
    for header in ("Precheck", "Recovery", "Verification"):
        assert text.count(header) >= 3, f"section '{header}' appears too few times"
