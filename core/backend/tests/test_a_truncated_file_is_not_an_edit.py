# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A file that came back half its length is a truncated answer, not an edit.

The Composer asks for `new_content` — "the COMPLETE file exactly as it should
be afterwards" — because asking for diffs produced diffs that would not apply.
Models do not always honour it. They return the interesting part and stop, or
they summarise the rest away.

`diff_from_new_content` believed them. Measured 2026-08-02 with the
effectiveness harness, eight tasks, every one applied cleanly:

    +15/-144    +5/-316    +20/-784    +2/-126

Those are not edits. That is a file being gutted, turned into a valid unified
diff, dry-run-approved, and applied. The Senior Judge scored it low and the
approval gate marked the run high-risk, so a person watching the panel would
have seen it — but the diff should never have been built in the first place,
and anything running unattended would have taken it.

The rule: an answer that drops most of a file is refused as an answer, not
rendered as a deletion. Deleting a file's contents is a real thing to want,
and it is also what a truncated reply looks like — so when the two are
indistinguishable, the product refuses and says why.
"""

from __future__ import annotations

from app.composer import from_content


def _file(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


def test_a_reply_that_lost_most_of_the_file_is_refused():
    old = _file(200)
    new = _file(20)  # the model stopped early
    assert from_content.diff_from_new_content("a.py", old, new) == "", (
        "a truncated answer became a 180-line deletion that applies cleanly"
    )


def test_an_ordinary_edit_still_goes_through():
    old = _file(200)
    new = old.replace("line 7\n", "line 7 changed\n")
    diff = from_content.diff_from_new_content("a.py", old, new)
    assert diff and "line 7 changed" in diff


def test_a_substantial_but_believable_cut_is_allowed():
    """Refactors delete real code. The guard is for answers that vanish, not
    for edits that shrink a file."""
    old = _file(100)
    new = _file(70)
    assert from_content.diff_from_new_content("a.py", old, new) != ""


def test_a_short_file_is_not_measured_by_ratio():
    """On a 6-line file, losing 4 lines is a normal edit and a ratio test
    would refuse it. Small files need a different rule, so they get one."""
    old = _file(6)
    new = _file(2)
    assert from_content.diff_from_new_content("a.py", old, new) != ""


def test_emptying_a_file_is_still_refused_when_it_looks_like_truncation():
    old = _file(300)
    assert from_content.diff_from_new_content("a.py", old, "") == ""


def test_growing_a_file_is_never_suspicious():
    old = _file(50)
    new = _file(400)
    assert from_content.diff_from_new_content("a.py", old, new) != ""
