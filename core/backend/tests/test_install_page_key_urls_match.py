# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The install page and the product must name the same console.

`HOW_TO_GET` is where "where do I get a key" is answered inside the product —
the editor's picker reads it over MCP, so those two cannot drift. The install
page cannot: it is a static page rendered before anyone has a server to ask,
so it carries its own copy of the URLs.

A copy that nothing checks is a copy that goes stale, and this one goes stale
in the worst place: the page somebody reads *before* they have anything
working. So the check lives here rather than in a reviewer's memory.

This does not test prose. It tests that every console URL the page shows is one
the product would actually send someone to.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.capabilities import FREE_TO_START, HOW_TO_GET

PAGE = (
    Path(__file__).resolve().parents[3]
    / "core"
    / "landing"
    / "app"
    / "docs"
    / "install"
    / "page.tsx"
)

# A domain-ish token: enough to catch "console.groq.com/keys" and
# "aistudio.google.com/apikey" without matching ordinary prose.
_URLISH = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[a-z0-9-]+)*\b")


def _known_urls() -> set[str]:
    found: set[str] = set()
    for sentence in HOW_TO_GET.values():
        found |= {m.group(0).rstrip(".") for m in _URLISH.finditer(sentence)}
    return found


@pytest.mark.skipif(not PAGE.exists(), reason="landing not checked out")
def test_every_console_the_page_names_is_one_we_would_send_people_to():
    text = PAGE.read_text(encoding="utf-8")
    # Only what the page presents as a place to go: <code> spans.
    shown = {
        m.rstrip(".")
        for code in re.findall(r"<code>([^<]+)</code>", text)
        for m in [code.strip()]
        if _URLISH.fullmatch(m.strip().rstrip("."))
    }
    known = _known_urls()
    # Belongs to the install itself, not to a provider console. `install.sh`
    # and `.env` are filenames the domain pattern cannot tell from a host.
    local = {"localhost:8000", ".env", "docker", "ollama.com", "install.sh"}
    stray = {s for s in shown if s not in known and s not in local}
    assert stray == set(), (
        f"the install page sends people to {sorted(stray)}, which HOW_TO_GET "
        "does not know about — one of the two is out of date"
    )


@pytest.mark.skipif(not PAGE.exists(), reason="landing not checked out")
def test_the_page_names_at_least_the_free_first_key():
    """Somebody reading this before they own anything needs the free path."""
    text = PAGE.read_text(encoding="utf-8").lower()
    assert "groq" in text and "console.groq.com" in text, (
        "the page tells people to add a key without saying where the free one is"
    )
    assert "no" in text and "card" in text, "the 'no card needed' point is the hook"
    # And it must not be quietly recommending a paid provider as the first step.
    first_paid = min(
        (text.index(p) for p in ("anthropic", "openrouter") if p in text),
        default=len(text),
    )
    assert text.index("groq") < first_paid, "a paid key was offered before a free one"


def test_free_tiers_the_page_leans_on_are_still_marked_free():
    for provider in ("groq", "cerebras", "gemini"):
        assert provider in FREE_TO_START, (
            f"{provider} is no longer free to start, and the install page still "
            "tells people it needs no card"
        )
