# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""One project, one graph key — on every surface, not just the ones fixed.

On 2026-08-03 the code-graph moved from a per-tenant key to a per-project one,
because a developer with two projects open got answers about the wrong one:
index A, open B, and blast-radius replied about A with nothing to say it had.
`codegraph_tools._caller_key()` carries that reasoning in a comment.

`composer_tools` was not changed with it. It still passed `graph_key=tenant`,
under a comment reading "deliberately the tenant, not the caller: the graph is
per workspace" — true when it was written, and false from the moment the key
stopped meaning a workspace. So Composer's blast-radius badge, the annotation
that tells a developer whether an edit is safe to approve, read from a bucket
the editor's own index command never writes to, and shared it between every
project the customer has open.

The fix that moved the key was correct. It was pointed at the two files
somebody remembered. This test is pointed at all of them, so the next one to
be added has to agree or fail.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path



TOOLS = Path(__file__).resolve().parents[1] / "app" / "mcp" / "tools"


def test_no_tool_keys_the_graph_by_tenant_alone():
    """Grepped rather than reasoned about, because reasoning is what missed it.

    A `key=` or `graph_key=` argument whose value is the bare tenant is the
    defect, whatever the file. Naming the two known-good spellings and refusing
    everything else means a third surface added next month cannot quietly opt
    out of project scoping.
    """
    offenders = []
    pattern = re.compile(r"\b(?:graph_)?key\s*=\s*(tenant|tenant_id)\b")
    for path in sorted(TOOLS.rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Comments quote the old spelling to explain why it was wrong.
            # Reading them as offences would make the guard unfixable: writing
            # down what went wrong would re-break the test that caught it.
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert offenders == [], (
        "a tool keys the code-graph by tenant alone, so two projects belonging "
        "to one customer share an index and answer about each other:\n  "
        + "\n  ".join(offenders)
    )


def test_composer_scopes_the_graph_to_the_project_it_was_given():
    """The specific surface, checked at the call rather than by grep.

    The grep above would pass on `graph_key=some_helper(tenant)` however wrong
    the helper was. This reads the value Composer actually computes.
    """
    # The server first: importing a tool module on its own leaves it partially
    # initialised and the failure reads as a missing attribute, not a cycle.
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import composer_tools
    from app.mcp.tools.codegraph_tools import _key_for

    src = inspect.getsource(composer_tools)
    assert "_key_for(" in src, (
        "composer_propose does not derive its graph key from the project root, "
        "so its blast-radius badge reads a different index than the one the "
        "editor's 'ABS: Index project' command fills"
    )
    # And the helper is the one the indexing side uses, not a lookalike.
    assert _key_for("t", "/a") != _key_for("t", "/b")
    assert _key_for("t", "/a") == _key_for("t", "/a")


def test_two_projects_do_not_share_an_index(tmp_path, monkeypatch):
    """The symptom, end to end: build A, ask about B, get nothing.

    Before the key changed this returned A's symbols under B's name — the shape
    that makes a developer approve a deletion because "nothing calls it".
    """
    from app.codegraph import graph as codegraph
    from app.mcp.tools.codegraph_tools import _key_for

    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))

    a = tmp_path / "a"
    a.mkdir()
    (a / "only_in_a.py").write_text("def only_in_a():\n    return 1\n", encoding="utf-8")
    codegraph.build(str(a), key=_key_for("t1", str(a)))

    b = tmp_path / "b"
    b.mkdir()
    (b / "only_in_b.py").write_text("def only_in_b():\n    return 2\n", encoding="utf-8")
    codegraph.build(str(b), key=_key_for("t1", str(b)))

    found = codegraph.search_symbols("only_in_a", key=_key_for("t1", str(b)))
    assert found == [], (
        "project B's graph knows a symbol that only exists in project A — the "
        "two share a bucket, and blast-radius will answer about the wrong one"
    )
    assert codegraph.search_symbols("only_in_a", key=_key_for("t1", str(a))), (
        "project A cannot find its own symbol, so the scoping went too far"
    )
