# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The licence email is the whole product for a self-hosted customer, and it
is the one message that arrives exactly once.

Audited 08-01: every template told the buyer to run ``install.sh`` "from the
package you downloaded" and linked to a guide at /docs/install. They had
downloaded nothing — no download was offered anywhere — and the guide route
did not exist. Money in, a key, and two dead ends.

These tests hold the delivery promise together: whatever the email tells
someone to do, the thing it points at has to be real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "email" / "templates"
LICENCE_TEMPLATES = sorted(TEMPLATES.glob("license_delivery*.html"))

# The landing app that has to answer the links the email hands out.
LANDING_APP = Path(__file__).resolve().parents[2] / "landing" / "app"


def test_there_are_licence_templates_to_check():
    assert LICENCE_TEMPLATES, f"no licence templates under {TEMPLATES}"


@pytest.mark.parametrize("path", LICENCE_TEMPLATES, ids=lambda p: p.name)
def test_a_licence_email_says_where_to_download(path: Path):
    """Telling somebody to run a file is only instructions if they have it.

    Read from the RENDERED mail rather than the template. The addresses moved
    into a setting on 08-03 — the templates ask for `{{ download_url }}` now —
    and checking the source would pass while a variable nobody populated
    reached the customer as literal braces.
    """
    from app.email.sender import _render

    lang = path.stem.rsplit("_", 1)[-1]
    _subject, body = _render(
        "license_delivery.html",
        lang=lang if lang in ("en", "tr", "es") else "en",
        license_key="ABS-TEST",
        refund_url="https://example.invalid/refund",
        customer_email="buyer@example.invalid",
    )
    assert "install.sh" in body, "this template no longer describes the install"
    assert "/download" in body, (
        f"{path.name} tells the buyer to run install.sh but never says where "
        "the package comes from"
    )
    assert "{{" not in body, f"{path.name}: an unrendered variable reached the mail"
    # The repository is private and stays private, so a GitHub Releases link
    # would 404 for every customer — the same defect this file exists to stop.
    assert "github.com" not in body, (
        f"{path.name} sends customers to GitHub; the source repo is private"
    )


@pytest.mark.parametrize("path", LICENCE_TEMPLATES, ids=lambda p: p.name)
def test_the_guide_the_email_promises_exists(path: Path):
    """The link was live in production and 404'd — the page is part of the
    product, not a nice-to-have, so its absence should break a test rather
    than a customer."""
    body = path.read_text(encoding="utf-8")
    if "/docs/install" not in body:
        pytest.skip("this template does not link the guide")
    page = LANDING_APP / "docs" / "install" / "page.tsx"
    assert page.exists(), (
        f"{path.name} links /docs/install; {page} does not exist"
    )


@pytest.mark.parametrize("path", LICENCE_TEMPLATES, ids=lambda p: p.name)
def test_the_key_and_a_way_back_to_us_are_both_in_the_email(path: Path):
    body = path.read_text(encoding="utf-8")
    assert "{{ license_key }}" in body, "the thing they paid for"
    assert "info@automatiabcn.com" in body, "a person to write to"


@pytest.mark.parametrize("path", LICENCE_TEMPLATES, ids=lambda p: p.name)
def test_the_download_page_the_email_promises_exists(path: Path):
    """Whatever surface the email points at has to be one we actually serve.
    Moved from GitHub Releases to our own domain on 08-01 when the repository
    was kept private — a private repo's releases are not downloadable."""
    body = path.read_text(encoding="utf-8")
    if "/download" not in body:
        pytest.skip("this template does not link the download page")
    page = LANDING_APP / "download" / "page.tsx"
    assert page.exists(), f"{path.name} links /download; {page} does not exist"
