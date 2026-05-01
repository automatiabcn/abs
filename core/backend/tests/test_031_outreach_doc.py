"""031 Modul C — Outreach templates doc presence + sections."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "marketing"
    / "outreach-templates.md"
)


def test_outreach_doc_present_and_long_enough():
    assert DOC.exists(), f"missing outreach doc at {DOC}"
    body = DOC.read_text(encoding="utf-8")
    assert len(body.split()) >= 800, "outreach doc too short"


def test_outreach_doc_contains_all_required_sections():
    body = DOC.read_text(encoding="utf-8").lower()
    for keyword in (
        "linkedin",
        "twitter",
        "hacker news",
        "cold email",
        "reddit",
        "demo video",
    ):
        assert keyword in body, f"section missing: {keyword}"
