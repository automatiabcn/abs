# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Context selection in a repo too big to send whole.

Differentiator #6 is monorepo-scale context: a persistent symbol graph instead
of a stale re-index. Audited 2026-08-02, the graph was built and queried only
*after* the model had written its edits, to draw the blast-radius badge. What
the model got to READ was decided by term matching on the task sentence alone.

The first version of this test assumed the callers would be invisible to term
matching. They are not: a file that calls `apply_discount` contains the string
`apply_discount`, so if the task names the symbol, the caller matches too. The
real failure is narrower and worse, because it only shows up at scale — the
caller matches with score 1, so does every unrelated file that happens to use
the word, the tie breaks alphabetically, and on a repo bigger than the context
budget the one file that actually breaks loses its slot to noise.

So the seeds are still chosen lexically — deterministic, local, no model call —
and the graph then says which of the candidates genuinely depend on them.
Pinned here:

* the dependent wins its slot against same-scoring noise;
* the budget is unchanged: neighbours compete for the existing slots rather
  than adding new ones, because a context window is not elastic;
* a file the task names by hand still leads;
* no graph, or a graph that throws, degrades to the old behaviour instead of
  taking the run down with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.codegraph import graph as codegraph
from app.composer import runtime


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """One definition, one real caller, and a crowd that merely says the word.

    Every noise file scores exactly what the caller scores. Only the graph can
    tell them apart, which is the point.
    """
    (tmp_path / "discount.py").write_text(
        "def apply_discount(total, pct):\n"
        "    return total - (total * pct / 100)\n",
        encoding="utf-8",
    )
    (tmp_path / "billing.py").write_text(
        "from discount import apply_discount\n\n\n"
        "def invoice(total):\n"
        "    return apply_discount(total, 10)\n",
        encoding="utf-8",
    )
    for i in range(10):
        # Mentions the term in a comment; calls nothing, so no graph edge.
        (tmp_path / f"aa_note_{i}.py").write_text(
            f"# notes about apply_discount, case {i}\n"
            f"def unrelated_{i}():\n    return {i}\n",
            encoding="utf-8",
        )
    return tmp_path


def _picked(root: Path, task: str, key: str | None) -> list[str]:
    files = runtime.workspace_files(str(root))
    return [
        rel for rel, _body in runtime.relevant_files(str(root), task, files, graph_key=key)
    ]


def test_the_file_that_breaks_wins_its_slot_against_noise(workspace, tmp_path, monkeypatch):
    key = f"test-{tmp_path.name}"
    codegraph.build(str(workspace), key=key)
    monkeypatch.setattr(runtime, "_MAX_CONTEXT_FILES", 3)

    task = "change apply_discount to take a fraction"
    without = _picked(workspace, task, None)
    with_graph = _picked(workspace, task, key)

    assert "billing.py" not in without, (
        "if term matching already wins this slot the test proves nothing — the "
        "fixture has to be one where the caller genuinely loses on a tie"
    )
    assert "billing.py" in with_graph, (
        "the file that breaks when this symbol changes lost its place to a "
        "comment, while the badge under the diff called it affected"
    )
    assert len(with_graph) == 3, "the budget was widened instead of re-spent"


def test_the_lexically_named_file_still_leads(workspace, tmp_path):
    key = f"test-lead-{tmp_path.name}"
    codegraph.build(str(workspace), key=key)
    picked = _picked(workspace, "change discount handling", key)
    assert picked[0] == "discount.py", (
        "a file the task names by hand outranks anything inferred from an edge"
    )


def test_a_broken_graph_does_not_break_the_run(workspace, monkeypatch, tmp_path):
    def _boom(*_a, **_k):
        raise RuntimeError("graph db is locked")

    task = "change apply_discount to take a fraction"
    expected = _picked(workspace, task, None)  # the old ranking, graph untouched

    monkeypatch.setattr(codegraph, "blast_radius", _boom)
    picked = _picked(workspace, task, f"test-boom-{tmp_path.name}")

    assert picked, "an annotation failure took the whole run with it"
    assert picked == expected, (
        "a failing graph has to degrade to the ranking we had before it "
        "existed, not to some third thing"
    )


def test_no_graph_key_leaves_the_ranking_alone(workspace, tmp_path):
    key = f"test-off-{tmp_path.name}"
    codegraph.build(str(workspace), key=key)
    task = "change apply_discount to take a fraction"
    assert _picked(workspace, task, None) != _picked(workspace, task, key), (
        "with the graph off the ranking must be exactly the old one — if the "
        "two agree here, the graph is not doing anything"
    )
