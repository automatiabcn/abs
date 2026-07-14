"""docs/billing-runbook.md guard."""

from __future__ import annotations

from pathlib import Path


def _docs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs"


def test_billing_runbook_exists_and_min_500_words():
    doc = _docs_dir() / "billing-runbook.md"
    assert doc.is_file(), f"runbook eksik: {doc}"
    text = doc.read_text(encoding="utf-8")
    word_count = len(text.split())
    assert word_count >= 500, f"runbook < 500 kelime: {word_count}"
    # at least 6 main sections (starting with ##)
    sections = [line for line in text.splitlines() if line.startswith("## ")]
    assert len(sections) >= 6, f"6 ana bölüm bulunamadı: {len(sections)}"
