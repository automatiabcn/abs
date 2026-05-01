"""030 Modul C — DRAFT banner present on all 4 legal docs + README."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOCS = [
    REPO / "docs" / "legal" / "dpa-template.md",
    REPO / "docs" / "legal" / "subprocessors.md",
    REPO / "docs" / "legal" / "privacy-policy.md",
    REPO / "docs" / "data-retention-policy.md",
]
README = REPO / "docs" / "legal" / "README.md"


def test_all_four_legal_docs_carry_draft_banner():
    for path in DOCS:
        assert path.exists(), f"missing doc: {path}"
        head = path.read_text(encoding="utf-8")[:600]
        assert "DRAFT — LEGAL REVIEW REQUIRED" in head, (
            f"banner missing in {path}"
        )
        assert "docs/legal/README.md" in head, (
            f"banner does not reference README in {path}"
        )


def test_banner_text_warns_no_liability_for_unreviewed_use():
    sample = DOCS[0].read_text(encoding="utf-8")[:600]
    assert "no liability" in sample.lower()
    assert "qualified legal counsel" in sample.lower()


def test_legal_review_readme_present_with_checklist():
    assert README.exists(), f"missing legal README at {README}"
    body = README.read_text(encoding="utf-8")
    assert len(body.split()) >= 250, "README too short — should be ~400 words"
    lower = body.lower()
    assert "checklist" in lower
    assert "counsel" in lower
