# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The truncation guard sat on one of the two doors.

On 2026-08-02 the effectiveness harness measured Composer gutting files —
+20/-784 among them, every one applying cleanly — and the fix taught
`diff_from_new_content` to refuse an answer that had lost most of the file.

That fix covers the door the current prompt uses. It is not the only door.
`edit_diff` still accepts a `unified_diff` the model wrote itself, for "older
prompts, other callers", and nothing on that path measures how much of the
file the diff removes. A model that answers with a raw diff instead of the
complete file walks straight past the guard into validate, dry-run and the
editor's Approve button — which is precisely the sequence the August finding
described, minus the one check that was added to stop it.

Two doors into the same room. The guard was pointed at the one somebody
remembered, and a guard only covers the surface it was pointed at.

The second half of this file is about what the customer is told. The guard
refuses in `logger.info` and returns an empty string, and the docstring of the
first fix says the product "refuses and says why". It does not say why. It
does not say anything: the edit is dropped, `degraded` stays False because the
model *did* produce edits, and the run comes back carrying the model's own
summary — a paragraph describing changes that are not in the response. A
customer reads "refactored the parser and removed the dead branch" above an
empty diff list and has no way to know the product protected them.
"""

from __future__ import annotations

import pytest

from app.composer import from_content
from app.composer import runtime as composer


def _file(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


def _deleting_diff(rel: str, first: int, count: int) -> str:
    """A well-formed unified diff that removes `count` lines and adds nothing."""
    body = "".join(f"-line {i}\n" for i in range(first, first + count))
    return (
        f"--- a/{rel}\n"
        f"+++ b/{rel}\n"
        f"@@ -{first + 1},{count} +{first},0 @@\n"
        f"{body}"
    )


# --- door two: the model wrote the diff itself -----------------------------


def test_a_raw_diff_that_guts_the_file_is_refused(tmp_path):
    """The August defect, arriving through the other door."""
    path = tmp_path / "a.py"
    path.write_text(_file(200), encoding="utf-8")

    diff, built = from_content.edit_diff(
        {"unified_diff": _deleting_diff("a.py", 10, 160)},
        rel_path="a.py",
        abs_path=str(path),
    )
    assert diff == "", (
        "a model-written diff removed 160 of 200 lines and was proposed. The "
        "same reply through the new_content field is refused; this path had no "
        "check at all."
    )
    assert built is False


def test_an_ordinary_raw_diff_still_goes_through(tmp_path):
    path = tmp_path / "a.py"
    path.write_text(_file(200), encoding="utf-8")

    diff, _ = from_content.edit_diff(
        {"unified_diff": _deleting_diff("a.py", 10, 3)},
        rel_path="a.py",
        abs_path=str(path),
    )
    assert diff != "", "a three-line deletion is an edit, not a truncation"


def test_a_raw_diff_that_replaces_lines_is_not_a_deletion(tmp_path):
    """Removed lines only count when nothing takes their place.

    A rewrite shows as -100/+100 and is an ordinary edit. Counting minus lines
    alone would refuse every large refactor in the product.
    """
    path = tmp_path / "a.py"
    path.write_text(_file(200), encoding="utf-8")

    body = "".join(f"-line {i}\n" for i in range(10, 170))
    body += "".join(f"+rewritten {i}\n" for i in range(10, 170))
    diff, _ = from_content.edit_diff(
        {"unified_diff": f"--- a/a.py\n+++ b/a.py\n@@ -11,160 +11,160 @@\n{body}"},
        rel_path="a.py",
        abs_path=str(path),
    )
    assert diff != "", "a 160-line rewrite was mistaken for a 160-line deletion"


def test_a_short_file_is_not_measured_by_ratio_here_either(tmp_path):
    """Same rule as the other door: on a six-line file a ratio means nothing."""
    path = tmp_path / "a.py"
    path.write_text(_file(6), encoding="utf-8")

    diff, _ = from_content.edit_diff(
        {"unified_diff": _deleting_diff("a.py", 1, 4)},
        rel_path="a.py",
        abs_path=str(path),
    )
    assert diff != ""


def test_a_file_we_cannot_read_does_not_block_the_diff(tmp_path):
    """No file on disk means no ratio to measure — and a new-file diff is a
    normal thing to propose. The guard must not turn "unknown" into "refused"."""
    diff, _ = from_content.edit_diff(
        {"unified_diff": "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+a\n+b\n"},
        rel_path="new.py",
        abs_path=str(tmp_path / "new.py"),
    )
    assert diff != ""


# --- what the customer is told ---------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    from app.codegraph import graph as codegraph

    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "big.py").write_text(_file(200), encoding="utf-8")
    return ws


def _stub(monkeypatch, parsed):
    async def _fake(task, *, tenant_id, project_slug, user_subject, files=None, contents=None):
        return parsed, ["groq"], {}

    monkeypatch.setattr(composer, "_generate_edits", _fake)

    async def _fake_judge(diff, path=None, **_caller):
        return {"combined_score": 8.0, "llm_score": 8.0, "ast_score": None, "teaching": []}

    monkeypatch.setattr(composer, "judge_diff", _fake_judge)


def _run(workspace, monkeypatch, parsed):
    import asyncio

    _stub(monkeypatch, parsed)
    return asyncio.run(
        composer.run_composer(
            "tidy the parser",
            workspace_root=str(workspace),
            tenant_id="wtest",
            graph_key="wtest",
        )
    )


def test_a_run_whose_only_edit_was_refused_says_so(workspace, monkeypatch):
    """Silence reads as "the model had nothing to say".

    It had plenty to say; we threw it away for a good reason and told nobody.
    The customer sees an empty edit list under a confident summary and cannot
    tell a protected truncation from a model that found nothing to change.
    """
    run = _run(
        workspace,
        monkeypatch,
        {
            "summary": "Rewrote the parser and dropped the dead branch.",
            "edits": [{"path": "big.py", "new_content": _file(10)}],
        },
    )

    assert run.edits == []
    assert run.refused, (
        "an edit was refused as truncated and the run carries no trace of it"
    )
    assert "big.py" in run.refused[0]


def test_the_summary_does_not_describe_edits_that_were_thrown_away(
    workspace, monkeypatch
):
    """The model's paragraph survives its own edits being refused.

    "Rewrote the parser" above an empty list is worse than saying nothing: it
    reads as a product that lost the work, not one that refused it.
    """
    run = _run(
        workspace,
        monkeypatch,
        {
            "summary": "Rewrote the parser and dropped the dead branch.",
            "edits": [{"path": "big.py", "new_content": _file(10)}],
        },
    )

    assert "Rewrote the parser" not in run.summary, (
        "the run describes changes it is not proposing"
    )
    assert run.summary, "an empty summary explains even less than a wrong one"


def test_a_run_with_nothing_refused_is_unchanged(workspace, monkeypatch):
    """The reporting must not fire on the ordinary case.

    A warning that shows up on a normal run is a warning nobody reads by the
    time a real one arrives.
    """
    new = _file(200).replace("line 7\n", "line 7 changed\n")
    run = _run(
        workspace,
        monkeypatch,
        {"summary": "Changed line 7.", "edits": [{"path": "big.py", "new_content": new}]},
    )

    assert len(run.edits) == 1
    assert run.refused == []
    assert run.summary == "Changed line 7."
