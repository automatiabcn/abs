# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Opening a project has to change what the product knows.

The first feedback from a real install (2026-08-03): a provider was connected,
a project was open, and the chat answered as though the repository did not
exist. It did not — as far as that tool was concerned. Of the thirty-three
tools the editor calls, exactly one sent the workspace, so opening a project
made Composer project-aware and left everything else answering from general
knowledge.

The founder's rule after that: as soon as a project is open, every capability
works against it.

The repair is not thirty-three new arguments — that leaves the thirty-fourth
tool wrong again the day it is written. The editor states the workspace once
via `workspace_set`, and any tool that wants it asks. These tests pin the two
halves that have to hold: the server remembers what it was told, and the chat
actually uses it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "billing.py").write_text(
        "def compute_invoice_total(items, vat_rate=0.21):\n"
        '    """Invoice total with Catalan VAT."""\n'
        "    return round(sum(i.price * i.qty for i in items) * (1 + vat_rate), 2)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Ledger\nInvoicing for small studios. VAT lives in src/billing.py.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_server_remembers_which_project_is_open(project: Path):
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "u")
    assert current_workspace("t", "u") is None, "started with a workspace it was never told"

    set_workspace("t", "u", str(project))
    assert current_workspace("t", "u") == str(project.resolve())


def test_one_caller_cannot_see_another_callers_project(project: Path):
    """Two developers on one server are two workspaces, not one.

    A shared answer here would send one customer's file paths — and with the
    chat change, their file *contents* — to another.
    """
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "a")
    forget("t", "b")
    set_workspace("t", "a", str(project))
    assert current_workspace("t", "b") is None


def test_a_path_the_server_cannot_see_is_refused(tmp_path: Path):
    """The editor runs on the laptop; the server may be in a container.

    Storing a root that does not resolve would make every tool that trusts it
    quietly answer about nothing, which is harder to notice than an error.
    """
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "u")
    assert set_workspace("t", "u", str(tmp_path / "not-there")) is None
    assert current_workspace("t", "u") is None


def test_clearing_is_possible(project: Path):
    """"No folder open" is a state the editor has to be able to state."""
    from app.workspace.current import current_workspace, set_workspace

    set_workspace("t", "u", str(project))
    set_workspace("t", "u", "")
    assert current_workspace("t", "u") is None


def test_the_chat_retrieves_from_the_open_project(project: Path):
    """The reported bug, at the level where it was wrong.

    Composer's own retrieval is used on purpose: two implementations of "which
    files matter" drift, and the developer would get different context from the
    chat and the Composer for the same question.
    """
    from app.composer.runtime import relevant_files, workspace_files

    files = workspace_files(str(project))
    assert "src/billing.py" in files

    picked = relevant_files(
        str(project), "How is VAT calculated in this project?", files
    )
    assert picked, "retrieval found nothing in a two-file project"
    names = [rel for rel, _ in picked]
    assert "src/billing.py" in names
    body = dict(picked)["src/billing.py"]
    assert "vat_rate" in body, "the file was named but its contents were not read"


@pytest.mark.asyncio
async def test_workspace_set_reports_a_root_it_cannot_see(tmp_path: Path):
    """The customer has to be told, not left with a chat that stays generic.

    A server in a container cannot see the laptop's paths. Answering "ok" there
    would leave the developer wondering why nothing improved.
    """
    import app.mcp.server  # noqa: F401 — importing a tool module first is a
    # circular import; the server package has to be initialised before it.
    from app.mcp.tools.engine_panel_tools import workspace_set

    out = json.loads(await workspace_set(str(tmp_path / "nope")))
    assert out["ok"] is False
    assert out["error"] == "not_a_directory"
    assert "mounted" in out["detail"], "the message does not say what to do about it"


def test_the_chat_says_which_files_it_sent():
    """The panel's promise: a developer knows what they just sent.

    Context gathered silently breaks that more quietly than not gathering it,
    so the tool returns the list and the panel can show it.
    """
    import inspect

    import app.mcp.server  # noqa: F401 — see above.
    from app.mcp.tools import engine_panel_tools

    src = inspect.getsource(engine_panel_tools.cascade_ask)
    assert '"used_files"' in src, "the answer does not say which files went with it"


def test_symbol_search_can_be_scoped_to_one_project(tmp_path: Path, monkeypatch):
    """Two projects, the same symbol name, and only one of them is open.

    This searched everything the server had ever indexed. A developer with two
    repositories got the other one's hits with nothing to say which was which.
    """
    from app.config import settings
    from app.symbols.parser import parse_directory
    from app.symbols.store import bulk_insert, search

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    a = tmp_path / "alpha"
    b = tmp_path / "beta"
    for d in (a, b):
        d.mkdir()
        (d / "mod.py").write_text("def shared_name():\n    pass\n", encoding="utf-8")

    bulk_insert(parse_directory(str(a)))
    bulk_insert(parse_directory(str(b)))

    assert len(search("shared_name", limit=50)) == 2, "the fixture indexed nothing"
    assert len(search("shared_name", limit=50, under=str(a))) == 1
    assert len(search("shared_name", limit=50, under=str(b))) == 1


def test_scoping_does_not_match_a_sibling_with_a_longer_name(tmp_path: Path, monkeypatch):
    """/srv/app must not also scope /srv/application."""
    from app.config import settings
    from app.symbols.parser import parse_directory
    from app.symbols.store import bulk_insert, search

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    short = tmp_path / "app"
    longer = tmp_path / "application"
    for d in (short, longer):
        d.mkdir()
        (d / "m.py").write_text("def prefix_probe():\n    pass\n", encoding="utf-8")

    bulk_insert(parse_directory(str(short)))
    bulk_insert(parse_directory(str(longer)))

    assert len(search("prefix_probe", limit=50, under=str(short))) == 1


def test_scoping_survives_a_symlinked_path(tmp_path: Path, monkeypatch):
    """The two halves have to agree on how a path is spelled.

    The workspace is stored with realpath(); the indexer recorded whatever it
    was handed. On macOS /var is a symlink to /private/var, so a scope of
    /var/... against symbols recorded as /private/var/... matched nothing —
    no error, no results, and no hint that the filter was at fault.
    """
    from app.config import settings
    from app.symbols.parser import parse_directory
    from app.symbols.store import bulk_insert, search

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    real = tmp_path / "real"
    real.mkdir()
    (real / "m.py").write_text("def via_link():\n    pass\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real)

    bulk_insert(parse_directory(str(real)))
    # Scoped by the symlinked spelling, which is what an editor may report.
    assert len(search("via_link", limit=50, under=str(link))) == 1

    # And the other direction, which is the one that actually exercises the
    # indexer: indexed through the symlink, scoped by the real path. Without
    # realpath() in the parser this stores /link/... and the scope never
    # matches — the first version of this test only checked the query side and
    # passed happily with the indexer's resolution removed.
    other = tmp_path / "other"
    other.mkdir()
    (other / "m.py").write_text("def indexed_via_link():\n    pass\n", encoding="utf-8")
    other_link = tmp_path / "other-link"
    other_link.symlink_to(other)

    bulk_insert(parse_directory(str(other_link)))
    assert len(search("indexed_via_link", limit=50, under=str(other))) == 1


def test_an_unindexed_project_is_not_reported_as_having_no_callers(tmp_path: Path, monkeypatch):
    """"Nothing breaks" is a claim about the code. It has to have read it.

    blast_radius returned {"found": false, "total_affected": 0} for a project
    the graph had never seen — identical to the answer for a function that
    genuinely has no callers. A developer asking what breaks if they change
    something, and being told nothing, could delete a live function on the
    strength of it.
    """
    from app.codegraph import graph
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text(
        "def leaf():\n    pass\n\n\ndef caller():\n    leaf()\n", encoding="utf-8"
    )

    never_indexed = graph.blast_radius("leaf", key="never")
    assert never_indexed["indexed"] is False
    assert "not been indexed" in never_indexed["note"]

    graph.build(str(project), key="built")
    real = graph.blast_radius("leaf", key="built")
    assert real["indexed"] is True
    assert real["found"] is True

    # A symbol that truly is not there, in a project that truly was read.
    absent = graph.blast_radius("no_such_symbol_anywhere", key="built")
    assert absent["indexed"] is True, "a read project must not look unindexed"
    assert absent["found"] is False


def test_symbol_search_says_when_the_project_was_never_read(tmp_path: Path, monkeypatch):
    """Same distinction, same reason: empty is not an answer unless it read."""
    from app.config import settings
    from app.symbols.store import count_under

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    project = tmp_path / "proj"
    project.mkdir()
    (project / "m.py").write_text("def thing():\n    pass\n", encoding="utf-8")

    assert count_under(str(project)) == 0, "a project nothing indexed counts as zero"

    from app.symbols.parser import parse_directory
    from app.symbols.store import bulk_insert

    bulk_insert(parse_directory(str(project)))
    assert count_under(str(project)) > 0, "indexing did not register under the project"


@pytest.mark.asyncio
async def test_announcing_a_project_says_whether_it_was_ever_read(tmp_path: Path, monkeypatch):
    """The editor needs this in the same round trip to offer indexing once.

    Without it a developer meets an honest but unhelpful "not indexed yet" the
    first time they search, and has to discover that a command exists and where
    it lives. The server already knows the answer when it is told the project.
    """
    import app.mcp.server  # noqa: F401 — circular import guard, see above.
    from app.config import settings
    from app.mcp.tools.engine_panel_tools import workspace_set
    from app.symbols.parser import parse_directory
    from app.symbols.store import bulk_insert

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    project = tmp_path / "proj"
    project.mkdir()
    (project / "m.py").write_text("def thing():\n    pass\n", encoding="utf-8")

    before = json.loads(await workspace_set(str(project)))
    assert before["ok"] is True
    assert before["indexed"] is False, "a project nothing has read cannot be indexed"

    bulk_insert(parse_directory(str(project)))

    after = json.loads(await workspace_set(str(project)))
    assert after["indexed"] is True, "an indexed project is still reported unread"


@pytest.mark.asyncio
async def test_indexing_and_querying_agree_on_the_key(tmp_path: Path, monkeypatch):
    """A graph built for a project has to be the graph the query reads.

    The key gained the project on 2026-08-03, and the build derived it from
    whichever workspace had been announced. Those are the same in the normal
    flow and silently different when `workspace_set` never landed — an older
    server, or a path the container cannot see. The graph would go under the
    tenant-only key while every query looked under tenant+project, so the
    project stayed "not indexed" no matter how often somebody indexed it.

    Both orders are checked because both happen: the editor announces then
    offers indexing, and somebody running the command from the palette may
    have neither.
    """
    import app.mcp.server  # noqa: F401 — circular import guard.
    from app.config import settings
    from app.mcp.context import get_mcp_caller
    from app.mcp.tools.codegraph_tools import code_blast_radius, code_graph_build
    from app.workspace.current import forget, set_workspace

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"), raising=False)

    try:
        t, u = get_mcp_caller()
    except Exception:  # noqa: BLE001
        t, u = None, None
    tenant, user = str(t or "default"), str(u or "")

    def make(name: str) -> Path:
        d = tmp_path / name
        (d / "src").mkdir(parents=True)
        (d / "src" / "m.py").write_text(
            "def leaf():\n    pass\n\n\ndef caller():\n    leaf()\n", encoding="utf-8"
        )
        return d

    # Announce, then index, then ask — the editor's order.
    first = make("announced-first")
    set_workspace(tenant, user, str(first))
    await code_graph_build(str(first))
    out = json.loads(await code_blast_radius("leaf"))
    assert out["indexed"] is True
    assert out["found"] is True, "the graph just built is not the one being read"

    # Index, then announce — the palette's order, and the one that used to
    # write the graph somewhere the query never looked.
    second = make("indexed-first")
    forget(tenant, user)
    await code_graph_build(str(second))
    set_workspace(tenant, user, str(second))
    out2 = json.loads(await code_blast_radius("leaf"))
    assert out2["indexed"] is True
    assert out2["found"] is True, "indexing before announcing lost the graph"
