"""new markdown files under docs/ + min word count guard."""

from __future__ import annotations

from pathlib import Path


def _docs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs"


def test_index_md_exists_min_150_words():
    p = _docs_dir() / "index.md"
    assert p.is_file()
    assert len(p.read_text(encoding="utf-8").split()) >= 150


def test_setup_guide_min_500_words():
    p = _docs_dir() / "setup-guide.md"
    assert p.is_file()
    assert len(p.read_text(encoding="utf-8").split()) >= 500


def test_api_reference_exists_min_500_words():
    p = _docs_dir() / "api-reference.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert len(text.split()) >= 500
    # Has auto-generated note
    assert "scripts/gen_api_reference.py" in text


def test_troubleshooting_min_400_words():
    p = _docs_dir() / "troubleshooting.md"
    assert p.is_file()
    assert len(p.read_text(encoding="utf-8").split()) >= 400


def test_faq_min_300_words_and_15_questions():
    p = _docs_dir() / "faq.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert len(text.split()) >= 300
    # Numbered questions ###1.…15.
    h3_lines = [line for line in text.splitlines() if line.startswith("### ")]
    assert len(h3_lines) >= 15


def test_changelog_documents_every_shipped_version():
    # This used to check for our internal task ids ("Task 010"). A customer
    # reading the changelog needs the versions they can actually install, and a
    # public repo should not carry our task numbering at all.
    p = _docs_dir() / "CHANGELOG.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    for version in (
        "## 1.0.6",
        "## 1.0.4",
        "## 1.0.3",
        "## 1.0.1",
        "## 1.0.0",
        "## 0.1.0",
    ):
        assert version in text, f"CHANGELOG.md no longer documents {version}"
