# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What is taken out of a model's answer before the developer sees it, and
what in it is checked against the project.

Two things seen on screen (2026-08-28 / 09-01, RobotMarket):

* An answer that began "We need to request the file list.**Project
  overview**" (in Turkish) - the model's private reasoning channel, glued onto the answer
  by a provider that does not separate the two. The prompt cannot prevent
  it; only the parser can.
* "app/models.py:LINE" and "the `cart` route in app/routes.py" — a
  placeholder the model copied, and a route that does not exist. The prompt
  says "never a placeholder" and "never invent"; a mid-size model still does
  both. What the prompt cannot guarantee, a deterministic check after the
  answer can at least *mark*, so an invented reference is shown as
  unverified rather than as fact.

Both are pure functions over text so they are tested without a provider.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

# Reasoning channels, in the shapes providers actually leak them.
_BLOCKS = re.compile(
    r"<(think|thinking|analysis|reasoning|reflection)>.*?</\1>\s*",
    re.S | re.I,
)
# OpenAI "harmony" tokens (gpt-oss): an analysis segment before the final one.
_HARMONY_ANALYSIS = re.compile(
    r"<\|channel\|>\s*analysis\s*<\|message\|>.*?"
    r"(?:(?:<\|end\|>\s*)?(?:<\|start\|>\s*assistant\s*)?<\|channel\|>\s*final\s*<\|message\|>|<\|end\|>)\s*",
    re.S,
)
_HARMONY_TOKENS = re.compile(r"<\|[a-z_]+\|>", re.I)
# A leading planning sentence in the model's own voice, immediately followed
# by the answer proper (markdown, a heading, a new line or a capital). Only
# at the very start, and only one sentence: a real answer that happens to
# begin "We need to add a route" keeps its second sentence and its meaning.
_LEAD_IN = re.compile(
    r"^\s*(?:(?:We|I)\s+(?:need|should|must|have|will|can|want|'ll|'d)(?:\s+to)?"
    r"|Let\s+me|Let's|The\s+(?:user|developer)\s+(?:asks|wants|is\s+asking|says|said))"
    r"[^\n]{0,240}?[.!?](?=\s*(?:\*\*|#|\n))\s*",
)


def strip_leaked_reasoning(text: str) -> str:
    """The answer without the model's reasoning channel, when one leaked."""
    if not text:
        return text
    out = _BLOCKS.sub("", text)
    out = _HARMONY_ANALYSIS.sub("", out)
    out = _HARMONY_TOKENS.sub("", out)
    out = _LEAD_IN.sub("", out, count=1)
    return out.lstrip() if out != text else text


_EXT = r"(?:py|ts|tsx|js|jsx|mjs|cjs|html|htm|md|json|css|scss|yml|yaml|toml|txt|sql|go|rs|java|kt|rb|php|sh|env|cfg|ini)"
# `app/models.py:LINE`, `app/models.py:LINE_NUMBER`, `app/models.py:N`
_PLACEHOLDER_LINE = re.compile(
    rf"(?P<path>[A-Za-z0-9_./-]+\.{_EXT}):(?P<ph>LINE(?:_NUMBER)?|N|NN|XX|\?+)\b"
)
# `app/routes.py:42` — a reference the panel turns into a link.
_PATH_LINE = re.compile(rf"(?<![\w/])(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.{_EXT}):(?P<line>\d{{1,6}})\b")
# A bare path in backticks: `app/cart.py`
_TICKED_PATH = re.compile(rf"`(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*/[A-Za-z0-9_.-]+\.{_EXT})`")


def normalise_rel(path: str) -> str:
    """`./app/x.py` → `app/x.py`; a leading `../` is kept so callers can refuse it."""
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _known(path: str, listing: Sequence[str]) -> bool:
    p = normalise_rel(path)
    if not p:
        return True
    for rel in listing:
        r = normalise_rel(rel)
        if r == p or r.endswith("/" + p):
            return True
    return False


def verify_references(
    text: str, listing: Iterable[str]
) -> Tuple[str, List[str]]:
    """(text with placeholders removed, references that are not in the project).

    `listing` is the project's file list (workspace-relative). With no
    listing — no project open, retrieval failed — nothing can be verified and
    nothing is marked: an empty list is not evidence that a file is missing.
    """
    if not text:
        return text, []
    files = list(listing or [])
    # 1. Placeholders: the path is still useful, the fake line is not.
    fixed = _PLACEHOLDER_LINE.sub(lambda m: m.group("path"), text)
    unverified: List[str] = []
    if not files:
        return fixed, unverified

    def note(p: str) -> None:
        if p not in unverified:
            unverified.append(p)

    # Code blocks are the model's proposal, not its claims about the project.
    prose = re.sub(r"```.*?```", " ", fixed, flags=re.S)
    for m in _PATH_LINE.finditer(prose):
        if not _known(m.group("path"), files):
            note(m.group("path"))
    for m in _TICKED_PATH.finditer(prose):
        if not _known(m.group("path"), files):
            note(m.group("path"))
    return fixed, unverified
