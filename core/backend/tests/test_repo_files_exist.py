"""Public repo files + README contents."""

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


def test_license_is_bsl_1_1():
    text = (_repo() / "LICENSE").read_text(encoding="utf-8")
    # BSL 1.1 since 2026-05-07
    assert "Business Source License 1.1" in text
    assert "Automatia BCN" in text
    assert "Change Date:" in text
    # Change License is Apache 2.0 (auto-flip on Change Date)
    assert "Apache License" in text and "Version 2.0" in text


# README contents


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
    # Pricing plans.
    #
    # This used to require "Self-Host Lifetime", "Maintenance", "Team Pack 5"
    # and "Team Pack 10" — the one-off model retired months before 2026-08-03.
    # So a test was not merely tolerating the stale pricing, it was *enforcing*
    # it: correcting the README to say what Stripe actually charges turned the
    # suite red, and the quickest way back to green was to put the wrong prices
    # back. A guard aimed at the past defends the past.
    for plan in ("Solo", "Team"):
        assert plan in text, f"README does not mention the {plan} plan"
    for amount in ("$29", "$19"):
        assert amount in text, f"README does not state {amount}"
    # And the retired model must not creep back.
    for gone in ("Self-Host Lifetime", "Team Pack", "$299"):
        assert gone not in text, f"README still advertises {gone}"
    # License badge / link (BSL 1.1 since legal switch 2026-05-07; Change Date
    # 2030-05-07 reverts to Apache 2.0)
    assert "BSL 1.1" in text or "Business Source License" in text
    # Multi-language switcher
    assert "README.tr.md" in text
    assert "README.es.md" in text
