# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The product has one name, and the company keeps its own.

Until 2026-08-03 a customer walking from the product page to the sign-in page
to the receipt read three names — "ABS Studio", "Automatia ABS" and "ABS
Server" — and the pricing page managed two in a single title, because the
site-wide title suffix said one thing while the newer pages said another.
Somebody about to pay cannot tell what they are buying.

Founder's decision (08-03): **ABS Studio**. `Automatia BCN` stays where it
belongs — the company that signs the terms and takes the money, not the thing
being sold.

This is pinned because a rename is exactly the kind of change that half-lands:
one surface gets it, another is remembered a week later, and the customer meets
the half that was forgotten.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EMAILS = ROOT / "core" / "backend" / "app" / "email"
LANDING = ROOT / "core" / "landing"

RETIRED = ("Automatia ABS", "ABS Server")


def _customer_files():
    if EMAILS.exists():
        yield from EMAILS.rglob("*.html")
        yield from EMAILS.rglob("*.txt")
    for sub in ("app", "components"):
        d = LANDING / sub
        if d.exists():
            for p in d.rglob("*.tsx"):
                yield p
    # The READMEs were missing from this list until 2026-08-03, and that is
    # exactly where the retired name survived: "Automatia ABS" was still the
    # first line of all three, in the repository the product ships from, while
    # this test stayed green. A guard only covers the surfaces it was pointed
    # at, and it had been pointed at the ones already fixed.
    for name in ("README.md", "README.tr.md", "README.es.md"):
        p = ROOT / name
        if p.exists():
            yield p
    # And the translated strings. The live privacy policy — a legal page, in
    # three languages — still said "the Automatia ABS product" on 2026-08-03,
    # because its text comes from locales/*.json and this guard only read .tsx.
    # The page was checked; the sentence it renders was not.
    locales = LANDING / "locales"
    if locales.exists():
        yield from locales.glob("*.json")
    # The backend's own strings. The guard read .md, .tsx and .json, and the
    # retired name was still in seven Python literals a customer meets: the
    # OpenAPI title, the MCP server's name and description — which every MCP
    # client prints on connect — the X-Title sent to OpenRouter with each call,
    # the GitHub App's name, system_status, and the header of the GDPR data
    # export, which is the file a customer downloads with their own data in it.
    backend_app = ROOT / "core" / "backend" / "app"
    if backend_app.exists():
        yield from sorted(backend_app.rglob("*.py"))


@pytest.mark.skipif(not EMAILS.exists(), reason="backend emails not checked out")
def test_no_retired_name_reaches_a_customer():
    offenders = []
    for path in _customer_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in RETIRED:
            if name in text:
                offenders.append(f"{path.relative_to(ROOT)}: {name}")
    assert offenders == [], (
        "a retired product name is still on a surface a customer sees:\n  "
        + "\n  ".join(sorted(offenders)[:20])
    )


@pytest.mark.skipif(not EMAILS.exists(), reason="backend emails not checked out")
def test_turkish_suffixes_agree_with_the_new_name():
    """A blanket rename would have produced "ABS Studio'ye".

    Turkish suffixes follow the last vowel, and "Studio" ends in a back rounded
    one: dative is 'ya, genitive 'nun, accusative 'yu. The front-vowel forms
    are what a find-and-replace leaves behind, and they read as broken to every
    Turkish customer on the list.
    """
    wrong = re.compile(r"ABS Studio'(ye|e|in|nin|i|te|de|ten|den)\b")
    offenders = []
    for path in _customer_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in wrong.finditer(text):
            offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)}")
    assert offenders == [], (
        "a suffix from the old name survived the rename:\n  " + "\n  ".join(offenders[:20])
    )


@pytest.mark.skipif(not (LANDING / "app").exists(), reason="landing not checked out")
def test_the_company_name_survived():
    """The rename must not have eaten the entity that signs the terms."""
    terms = LANDING / "app" / "terms" / "page.tsx"
    if terms.exists():
        assert "Automatia BCN" in terms.read_text(encoding="utf-8")
    footer = LANDING / "components" / "Footer.tsx"
    if footer.exists():
        assert "Automatia BCN" in footer.read_text(encoding="utf-8")
