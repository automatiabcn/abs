# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Nothing on a customer surface may claim that nothing leaves the server.

Six surfaces said it on 2026-08-03 — the pricing page ("Runs on your own
server; nothing reaches us", a bullet added that same day), the site FAQ
("Nothing reaches an Automatia server"), the hero's big "0", and all three
READMEs. One of them was mine, written hours earlier.

It is false. `app/licensing/phone_home.py` contacts a hardcoded activation
endpoint on start-up and once every 24 hours, sending the licence id, a hashed
machine fingerprint, the build hash, the instance URL and the version. No
customer content — but "nothing" is not "no content", and the difference is
the one a customer discovers in their own outbound firewall log, at which
point every other claim on the page is worth less.

Two things make the true version easy to say and worth saying: it only happens
once a licence key is configured, so a trial sends nothing at all, and
`ABS_PHONE_HOME_DISABLED=1` turns it off.

So the rule is narrow: an absolute claim is banned, a claim about *customer
data* is fine. "None of your data reaches us" is true and is what the pages say
now.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LANDING = ROOT / "core" / "landing"

# Sentences that say "nothing at all", in the three languages we ship.
_ABSOLUTE = [
    re.compile(r"nothing reaches", re.I),
    re.compile(r"nothing (?:is )?(?:ever )?(?:sent|leaves)", re.I),
    re.compile(r"hiçbir şey ulaşmaz", re.I),
    re.compile(r"hiçbir şey (?:gönderilmez|çıkmaz)", re.I),
    re.compile(r"nada llega", re.I),
    re.compile(r"nada (?:se envía|sale)", re.I),
]


def _surfaces():
    for name in ("README.md", "README.tr.md", "README.es.md"):
        p = ROOT / name
        if p.exists():
            yield p
    for sub in ("app", "components"):
        d = LANDING / sub
        if d.exists():
            yield from sorted(d.rglob("*.tsx"))
    locales = LANDING / "locales"
    if locales.exists():
        yield from sorted(locales.glob("*.json"))


def test_the_server_really_does_phone_home():
    """If this fails, the rule below is obsolete and should be deleted.

    A guard that outlives the thing it guards is worse than none: it stops
    people saying something that has become true.
    """
    src = (ROOT / "core" / "backend" / "app" / "licensing" / "phone_home.py")
    assert src.is_file(), "phone_home.py is gone — revisit this whole file"
    text = src.read_text(encoding="utf-8")
    assert "ACTIVATION_URL" in text and "https://" in text


def test_the_phone_home_stays_off_during_the_trial():
    """The reason we can describe this without embarrassment.

    Every page promises the seven days need no card and no licence key. If the
    activation call fired anyway, a trialling stranger would be reporting their
    machine fingerprint to us before they had agreed to anything.
    """
    text = (
        ROOT / "core" / "backend" / "app" / "licensing" / "phone_home.py"
    ).read_text(encoding="utf-8")
    assert 'token = (settings.license_key or "").strip()' in text
    assert "if not token:" in text, (
        "the heartbeat no longer checks for a licence key before sending — a "
        "trial would now phone home"
    )


def test_there_is_still_a_way_to_turn_it_off():
    """The FAQ names this variable. If it stops working, the FAQ starts lying."""
    text = (ROOT / "core" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "ABS_PHONE_HOME_DISABLED" in text


@pytest.mark.skipif(not LANDING.exists(), reason="landing not checked out")
def test_no_surface_claims_that_nothing_leaves():
    offenders: list[str] = []
    checked = 0
    for path in _surfaces():
        checked += 1
        for i, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            stripped = line.strip()
            # A comment recording the old wording is how we remember it was wrong.
            if stripped.startswith(("//", "*", "{/*", "<!--", "#")):
                continue
            for pattern in _ABSOLUTE:
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{i}: {stripped[:80]}")
                    break
    assert checked > 5, "this found almost no surfaces — the glob has rotted"
    assert offenders == [], (
        "these say nothing leaves the server, and the licence check does:\n  "
        + "\n  ".join(offenders)
        + "\n\nSay 'none of your data' instead — that one is true."
    )


def test_no_surface_claims_we_supply_provider_keys():
    """"Your keys or ours" was on the pricing page until 2026-08-03.

    Every provider slot in `infra/.env.example` is empty and the image ships
    none, so "or ours" promised something the customer would discover was
    missing on their first prompt — the worst possible moment, ninety seconds
    into a product they have just installed.

    The honest version sells better: the providers worth starting on (Groq,
    Gemini, Cerebras and four more) cost nothing to start on, which is what
    `FREE_TO_START` records.
    """
    env = ROOT / "infra" / ".env.example"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "_API_KEY=" in line and not line.strip().startswith("#"):
                _name, _, value = line.partition("=")
                assert value.strip() == "", (
                    f"{line.split('=')[0]} ships with a value — if we really do "
                    f"supply a key now, this guard and the copy both need to change"
                )

    for path in _surfaces():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "{/*", "<!--", "#")):
                continue
            assert not re.search(r"keys? or ours", line, re.I), (
                f"{path.relative_to(ROOT)}:{i} offers our keys, and we have none "
                f"to offer"
            )
