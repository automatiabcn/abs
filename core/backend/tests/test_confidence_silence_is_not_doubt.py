# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Saying nothing is not the same as saying "I am not sure".

The Composer panel draws a "◇ uncertain ×N" badge for every edit whose
`confidence` is under 0.5. `confidence` is the model's own self-report, and it
defaulted to 0.0 — so an edit where the model simply did not write the field
was rendered as an edit the model doubted.

That is the worst kind of warning: it fires on the common case, so it stops
meaning anything, and by the time a real low-confidence edit appears nobody
reads the badge any more. Absence of a claim and a claim of doubt are different
facts and are kept apart here.

Differentiator #3 in the pivot document is a real uncertainty signal: two or
more models disagreeing about a hunk. A single model's opinion of itself is not
that, and while it is what we have, it is labelled as what it is rather than
being presented as the product's own finding.
"""

from __future__ import annotations

from app.composer import runtime


def test_a_missing_self_report_is_unknown_not_zero():
    assert runtime._clamp01(None) is None, (
        "an edit the model said nothing about was rendered as an edit the "
        "model doubted"
    )
    assert runtime._clamp01("") is None
    assert runtime._clamp01("not a number") is None


def test_a_real_self_report_survives():
    assert runtime._clamp01(0.2) == 0.2
    assert runtime._clamp01(0) == 0.0, "an explicit zero IS a statement of doubt"
    assert runtime._clamp01(1.7) == 1.0, "still clamped"
    assert runtime._clamp01("0.4") == 0.4


def test_the_edit_carries_the_difference():
    from app.composer.schemas import ProposedEdit

    quiet = ProposedEdit(path="a.py", unified_diff="")
    assert quiet.confidence is None, (
        "the default has to be 'nobody said', or the panel invents doubt for "
        "every edit that omits the field"
    )
    unsure = ProposedEdit(path="a.py", unified_diff="", confidence=0.1)
    assert unsure.confidence == 0.1
