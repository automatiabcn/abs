"""An edit nobody graded is a reason to ask, not a pass.

Audit 2026-08-18: `_derive_risk` read `quality is not None and quality < 5`
as the only quality gate, so an edit with both judge legs None (judge quota
out, no judge provider) came back `risk: low, requires_approval: False`.
"""

from __future__ import annotations

from app.composer.runtime import _derive_risk
from app.composer.schemas import ProposedEdit


def _edit(**kw):
    base = dict(
        path="a.py", unified_diff="@@ -1 +1 @@\n-a\n+b\n", rationale="",
        judge_score=None, judge_correctness=None, judge_style=None, judge_notes=[],
        blast_radius={"total_affected": 0}, confidence=None,
        validation={"valid": True, "stage": "", "reason": "OK"}, dry_run_ok=True,
    )
    base.update(kw)
    return ProposedEdit(**base)


def test_ungraded_asks_for_approval():
    risk, approval = _derive_risk([_edit()])
    assert risk == "ungraded"
    assert approval is True


def test_a_graded_good_edit_is_low_and_free():
    risk, approval = _derive_risk([_edit(judge_score=8.5, judge_correctness=8.5)])
    assert (risk, approval) == ("low", False)


def test_ungraded_does_not_hide_a_dangerous_sibling():
    risk, approval = _derive_risk([_edit(), _edit(judge_score=2.0, judge_correctness=2.0)])
    assert (risk, approval) == ("high", True)


def test_ungraded_outranks_medium_blast():
    risk, approval = _derive_risk([_edit(blast_radius={"total_affected": 5})])
    assert (risk, approval) == ("ungraded", True)
