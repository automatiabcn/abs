"""031 Modul B — 5×3 beta email templates exist + structurally valid."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "email"
    / "templates"
)
STAGES = (
    "beta_welcome",
    "beta_walkthrough",
    "beta_first_success",
    "beta_check_in",
    "beta_renewal_offer",
)
LANGS = ("en", "tr", "es")


def test_all_15_beta_templates_present():
    missing = []
    for stage in STAGES:
        for lang in LANGS:
            path = TEMPLATES_DIR / f"{stage}_{lang}.html"
            if not path.exists():
                missing.append(path.name)
    assert not missing, f"missing templates: {missing}"


def test_each_template_has_jinja_placeholders_and_subject_comment():
    for stage in STAGES:
        for lang in LANGS:
            path = TEMPLATES_DIR / f"{stage}_{lang}.html"
            body = path.read_text(encoding="utf-8")
            assert body.lstrip().lower().startswith("<!doctype html>"), (
                f"{path.name}: missing DOCTYPE"
            )
            assert f'lang="{lang}"' in body, (
                f"{path.name}: missing lang=\"{lang}\""
            )
            assert "{{ customer_email }}" in body, (
                f"{path.name}: missing customer_email placeholder"
            )
            assert "{{ unsubscribe_url }}" in body, (
                f"{path.name}: missing unsubscribe_url placeholder"
            )
            assert "<!-- subject:" in body.lower(), (
                f"{path.name}: missing subject comment"
            )
