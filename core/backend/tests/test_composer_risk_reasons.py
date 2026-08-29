"""The risk badge carries its reasons.

"▲ high" over a one-line test addition, with nothing else, was either feared
or ignored (visual audit, 2026-08-28, U4). `derive_risk_with_reasons` says
why in words a developer can act on; the verdict itself is unchanged.
"""

from __future__ import annotations

from app.composer.runtime import _derive_risk, derive_risk_with_reasons
from app.composer.schemas import ProposedEdit


def _edit(path="app/x.py", *, score=8.0, correctness=None, affected=0, dry_run_ok=True):
    return ProposedEdit(
        path=path,
        diff="@@ -1 +1 @@\n-a\n+b\n",
        judge_score=score,
        judge_correctness=correctness,
        blast_radius={"total_affected": affected},
        dry_run_ok=dry_run_ok,
    )


def test_a_low_correctness_edit_says_so():
    risk, gate, why = derive_risk_with_reasons([_edit(correctness=3.4)])
    assert (risk, gate) == ("high", True)
    assert any("correctness 3.4 is below" in w for w in why)


def test_a_wide_blast_radius_says_how_many_places():
    risk, _, why = derive_risk_with_reasons([_edit(affected=40)])
    assert risk == "high"
    assert any("40 places depend" in w for w in why)


def test_a_diff_that_does_not_apply_says_so():
    _, _, why = derive_risk_with_reasons([_edit(dry_run_ok=False)])
    assert any("does not apply" in w for w in why)


def test_ungraded_is_named_as_asking_not_assuming():
    risk, gate, why = derive_risk_with_reasons([_edit(score=None)])
    assert risk == "ungraded" and gate is True
    assert any("nobody graded" in w for w in why)


def test_a_clean_small_edit_has_a_reassuring_reason_and_the_verdict_matches_the_old_one():
    edits = [_edit()]
    risk, gate, why = derive_risk_with_reasons(edits)
    assert (risk, gate) == _derive_risk(edits) == ("low", False)
    assert why == ["small, graded, applies cleanly"]
