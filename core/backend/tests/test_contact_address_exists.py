# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Every address we hand a customer has to be one that receives mail.

The pages and the licence emails told people to write to
support@automatiabcn.com — sixty-three times, across forty-one files. That
mailbox has not been bought (2026-08-02), and the site is live to real users.
An address that bounces is worse than no address: the reader believes they
have asked for help and then waits.

So the rule is not "use this particular address" — it is that every
automatiabcn.com address a customer can see appears in this list, and the list
only gains an entry when the mailbox behind it exists. Adding
support@automatiabcn.com back is a one-line change here, made the day it is
bought.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Mailboxes that exist and are read. Add an entry the day it is provisioned,
# not the day it is planned.
LIVE_MAILBOXES = {"info@automatiabcn.com"}

BACKEND = Path(__file__).resolve().parents[1]
LANDING = BACKEND.parent / "landing"

# Everywhere a customer's eyes can land. `docs/` is in the list because the
# first sweep missed it and the trademarks policy went on naming three
# mailboxes that may not exist — a legal document is exactly the page somebody
# reads when they most need a reply.
SURFACES = [
    BACKEND / "app" / "email" / "templates",
    LANDING / "app",
    LANDING / "components",
    BACKEND.parent.parent / "docs",
]

ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@automatiabcn\.com")


def _files():
    for root in SURFACES:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".html", ".tsx", ".ts", ".md"}:
                if "node_modules" in path.parts:
                    continue
                yield path


def test_there_are_surfaces_to_check():
    assert list(_files()), "no customer-facing files found — the guard is not guarding"


@pytest.mark.parametrize("path", sorted(_files()), ids=lambda p: p.name)
def test_a_customer_is_only_sent_to_a_mailbox_that_exists(path: Path):
    found = set(ADDRESS.findall(path.read_text(encoding="utf-8", errors="ignore")))
    unknown = found - LIVE_MAILBOXES
    assert not unknown, (
        f"{path.relative_to(BACKEND.parent)} points customers at {sorted(unknown)}, "
        f"which is not in LIVE_MAILBOXES. Either the mailbox now exists — add it "
        f"to the list — or the reader is being asked to write into a void."
    )
