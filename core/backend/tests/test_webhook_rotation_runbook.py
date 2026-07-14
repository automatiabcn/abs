"""Webhook rotation runbook completeness."""

from __future__ import annotations

from pathlib import Path


def test_webhook_rotation_runbook_min_words_and_sections():
    p = Path(__file__).resolve().parents[3] / "docs" / "webhook-rotation-runbook.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert len(text.split()) >= 600
    for section in (
        "Stripe webhook secret",
        "Slack signing secret",
        "GitHub App webhook secret",
        "Compromise scenario",
        "rotation schedule",
    ):
        assert section in text, f"missing: {section}"
    # Must include real commands
    assert "docker compose" in text
    assert "sops" in text
