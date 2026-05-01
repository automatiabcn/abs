"""032 Modul H — admin guide + telemetry primer present + structured."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ADMIN_GUIDE = REPO / "docs" / "operations" / "admin-guide.md"
TELEMETRY = REPO / "docs" / "operations" / "telemetry.md"


def test_admin_guide_present_with_required_sections():
    assert ADMIN_GUIDE.exists(), f"missing admin guide at {ADMIN_GUIDE}"
    body = ADMIN_GUIDE.read_text(encoding="utf-8")
    assert len(body.split()) >= 600, "admin guide too short"
    lower = body.lower()
    for kw in (
        "login",
        "ip",
        "checklist",
        "revoke",
        "troubleshoot",
    ):
        assert kw in lower, f"section keyword missing: {kw}"


def test_telemetry_primer_present_with_definitions():
    assert TELEMETRY.exists(), f"missing telemetry primer at {TELEMETRY}"
    body = TELEMETRY.read_text(encoding="utf-8")
    assert len(body.split()) >= 450, "telemetry primer too short"
    lower = body.lower()
    for kw in ("revenue", "retention", "churn", "compliance", "alert"):
        assert kw in lower, f"definition keyword missing: {kw}"
