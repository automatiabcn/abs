"""025 Modul A + G — Public repo files + README contents."""

from __future__ import annotations

from pathlib import Path


def _repo() -> Path:
    return Path(__file__).resolve().parents[3]


def test_top_level_files_exist():
    repo = _repo()
    for name in (
        "README.md",
        "README.tr.md",
        "README.es.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
    ):
        assert (repo / name).is_file(), f"missing: {name}"


def test_github_templates_exist():
    repo = _repo()
    issue_dir = repo / ".github" / "ISSUE_TEMPLATE"
    assert (issue_dir / "bug.yml").is_file()
    assert (issue_dir / "feature.yml").is_file()
    assert (issue_dir / "question.yml").is_file()
    assert (repo / ".github" / "pull_request_template.md").is_file()


def test_license_is_apache_2_0():
    text = (_repo() / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0" in text
    assert "Automatia BCN" in text


# Modul G — README contents

def test_readme_min_word_count_and_sections():
    text = (_repo() / "README.md").read_text(encoding="utf-8")
    word_count = len(text.split())
    assert word_count >= 500, f"README too short: {word_count} words"
    # Required sections
    for section in (
        "Why ABS",
        "Quick install",
        "Pricing",
        "License",
        "Tech stack",
    ):
        assert section in text, f"section missing: {section}"


def test_readme_lists_pricing_and_license_and_languages():
    text = (_repo() / "README.md").read_text(encoding="utf-8")
    # Pricing SKUs
    for sku in ("Self-Host Lifetime", "Maintenance", "Team Pack 5", "Team Pack 10"):
        assert sku in text
    # License badge / link
    assert "Apache 2.0" in text
    # Multi-language switcher
    assert "README.tr.md" in text
    assert "README.es.md" in text
