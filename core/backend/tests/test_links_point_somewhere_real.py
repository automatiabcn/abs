# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The links a paying customer follows have to resolve.

Found 2026-08-03 while walking the money path: the licence-delivery email —
the one thing a self-hosted customer actually buys — pointed its download and
install links at `abs.automatiabcn.com`, a host with no DNS record at all.
Money in, and the two links that matter dead. The refund link worked, because
it used the real host, so the only working link in the email was the one for
getting the money back.

The footer had already been fixed for exactly this, with a comment saying
"abs.automatiabcn.com does not resolve". One instance repaired, seventy-one
left — the class was never swept.

So the fix is a single source rather than another round of find-and-replace:
`settings.public_site_url` is injected into every template render, templates
ask for it by name, and this file refuses the dead host anywhere a customer
can see it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EMAILS = ROOT / "core" / "backend" / "app" / "email"

# Never resolved. Kept here by name so a paste from an old document is caught
# rather than quietly shipped.
DEAD_HOSTS = ("abs.automatiabcn.com", "status.abs.automatiabcn.com")


LANDING = ROOT / "core" / "landing"


def _customer_surfaces():
    """Everywhere a link can reach a person who is paying us.

    Emails were only half of it: the sweep on 08-03 found the dead host in the
    page shown right after payment, in the canonical URL, in robots.txt and in
    the sitemap. A guard that had checked emails alone would have passed while
    the money path stayed broken.
    """
    if EMAILS.exists():
        yield from EMAILS.rglob("*.html")
    for sub in ("app", "components"):
        d = LANDING / sub
        if not d.exists():
            continue
        for pattern in ("*.tsx", "*.ts"):
            for f in d.rglob(pattern):
                if "__tests__" in f.parts:
                    continue
                yield f


def test_no_customer_surface_links_to_a_host_that_does_not_exist():
    offenders = []
    for path in _customer_surfaces():
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            stripped = line.strip()
            # A comment naming the dead host is how we remember it was dead.
            if stripped.startswith(("//", "/*", "{/*", "*", "#", "<!--")):
                continue
            for host in DEAD_HOSTS:
                if host in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{i}")
    assert offenders == [], (
        "these would send a customer nowhere:\n  " + "\n  ".join(sorted(offenders)[:20])
    )


@pytest.mark.skipif(not EMAILS.exists(), reason="emails not checked out")
def test_no_email_sends_a_customer_to_a_host_that_does_not_exist():
    offenders = []
    for path in sorted(EMAILS.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for host in DEAD_HOSTS:
            if host in text:
                offenders.append(f"{path.name}: {host}")
    assert offenders == [], (
        "a customer who paid would follow these into nothing:\n  "
        + "\n  ".join(offenders[:20])
    )


@pytest.mark.skipif(not EMAILS.exists(), reason="emails not checked out")
def test_the_delivery_email_has_a_working_download_and_guide_link():
    """The two links this email exists to carry."""
    from app.email.sender import _render

    for lang in ("en", "tr", "es"):
        _subject, html = _render(
            "license_delivery.html",
            lang=lang,
            license_key="ABS-TEST",
            refund_url="https://example.invalid/refund",
            customer_email="buyer@example.invalid",
        )
        links = re.findall(r'href="([^"]+)"', html)
        assert any("/download" in l for l in links), f"{lang}: no download link"
        assert any("/docs/install" in l for l in links), f"{lang}: no install link"
        for link in links:
            for host in DEAD_HOSTS:
                assert host not in link, f"{lang}: {link} goes nowhere"
        # And nothing left unrendered — a customer reading "{{ license_key }}"
        # has been sent a template, not a licence.
        assert "{{" not in html, f"{lang}: an unrendered variable reached the mail"


def test_one_place_decides_the_public_address():
    """The reason this drifted is that there was no single source.

    Seventy-two files carried the host as a literal, so fixing one taught the
    others nothing.
    """
    from app.config import settings

    url = getattr(settings, "public_site_url", "")
    assert url, "there is no setting that says where the product lives"
    assert url.startswith("https://"), url
    for host in DEAD_HOSTS:
        assert host not in url, f"the single source points at a dead host: {url}"


def test_templates_ask_for_the_address_rather_than_repeating_it():
    """A literal in a template is a link that cannot be moved."""
    from app.email.sender import _render

    _subject, html = _render(
        "license_delivery.html",
        lang="en",
        license_key="k",
        refund_url="https://example.invalid/r",
        customer_email="b@example.invalid",
    )
    from app.config import settings

    assert getattr(settings, "public_site_url") in html, (
        "the delivery email does not use the configured address, so changing "
        "it would not change the email"
    )
