# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The number of providers we claim has to be the number we have.

"Seven providers, so one outage is not your outage" is a bullet on the pricing
page, and the same count appears in three READMEs and three locale files. On
2026-08-03 every one of them said **six**, while the cascade had seven cloud
providers and nine in total — so the copy was stale in our own disfavour, which
is why nobody had noticed. A wrong number on a sales page is the same defect
whichever way it points.

Counting is the part that drifts, so the count is derived here rather than
typed. What the customer is being told is how many *independent vendors* can
answer their request, so local runtimes are excluded: Ollama and MLX are their
machine, not a second company that stays up when the first one falls over.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LANDING = ROOT / "core" / "landing"


def _cloud_provider_count() -> int:
    from app.providers.cascade import LOCAL_PROVIDERS_ORDER, all_providers

    return len([p for p in all_providers() if p not in LOCAL_PROVIDERS_ORDER])


# "Seven", "7 providers", "7 sağlayıcı", "7 proveedores" — whichever way a
# surface spells it.
_WORDS = {
    3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten",
}


def _claims(text: str) -> list[str]:
    """Every provider count a surface states, as a bare number."""
    found: list[str] = []
    for m in re.finditer(
        r"\b(\d+|three|four|five|six|seven|eight|nine|ten)[\s-]*"
        r"(providers?|proveedores?|sağlayıcı)",
        text,
        re.IGNORECASE,
    ):
        word = m.group(1).lower()
        for n, w in _WORDS.items():
            if word == w:
                word = str(n)
                break
        found.append(word)
    return found


def _surfaces():
    for name in ("README.md", "README.tr.md", "README.es.md"):
        p = ROOT / name
        if p.exists():
            yield p
    tiers = LANDING / "components" / "PricingTiers.tsx"
    if tiers.exists():
        yield tiers
    locales = LANDING / "locales"
    if locales.exists():
        yield from sorted(locales.glob("*.json"))


def test_the_catalogue_has_not_quietly_changed_size():
    """If this fails, the copy below needs a decision, not a nudge."""
    assert _cloud_provider_count() == 7


@pytest.mark.skipif(not LANDING.exists(), reason="landing not checked out")
def test_no_surface_advertises_a_number_we_do_not_have():
    expected = str(_cloud_provider_count())
    offenders: list[str] = []
    checked = 0
    for path in _surfaces():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for claim in _claims(text):
            checked += 1
            if claim != expected:
                offenders.append(f"{path.relative_to(ROOT)}: says {claim}")
    assert checked > 0, "this found no provider claim anywhere — the regex has rotted"
    assert offenders == [], (
        f"the cascade has {expected} cloud providers; these say otherwise:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )
